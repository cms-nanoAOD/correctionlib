#include <sstream>
#include "rapidjson/writer.h"
#include "rapidjson/stringbuffer.h"
#include "lwtnn/LightweightNeuralNetwork.hh"
#include "lwtnn/parse_json.hh"
#include "correction.h"
#include "correction_detail.h"

using namespace correction;

class detail::LWTNNEvaluationContext {
  public:
    LWTNNEvaluationContext(const JSONObject& json, const Correction& context);
    double evaluate(const std::vector<Variable::Type>& values) const;

  private:
    // pointers to pointers to pointers to ...
    std::unique_ptr<const lwt::LightweightNeuralNetwork> nn_;
    std::vector<std::pair<std::string, size_t>> input_spec_;
    std::vector<std::string> output_names_;
    std::unique_ptr<Formula> finalizer_;
};

detail::LWTNNEvaluationContext::LWTNNEvaluationContext(const JSONObject& json, const Correction& context)
{
  const auto &blob = json.getRequiredValue("opaque");
  rapidjson::StringBuffer buffer;
  rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
  blob.Accept(writer);
  std::istringstream in(buffer.GetString());
  lwt::JSONConfig cfg;
  try {
    cfg = lwt::parse_json(in);

    for (const auto& input : cfg.inputs) {
      size_t idx = find_input_index(input.name, context.inputs());
      if ( context.inputs().at(idx).type() == Variable::VarType::string ) {
        throw std::runtime_error("LWTNN cannot use string inputs, but input '" + input.name + "' has string type");
      }
      input_spec_.emplace_back(input.name, idx);
    }

    std::vector<Variable> finalize_inputs;
    for (const auto& name : cfg.outputs) {
      output_names_.push_back(name);
      finalize_inputs.emplace_back(name, "", Variable::VarType::real);
    }
    if ( output_names_.empty() ) {
      throw std::runtime_error("LWTNN model has no outputs");
    }

    const auto& finalizer_data = json.getRequiredValue("finalizer");
    if ( finalizer_data.IsObject()
        && finalizer_data.HasMember("nodetype")
        && finalizer_data["nodetype"].IsString()
        && finalizer_data["nodetype"] == "formula"
      ) {
      finalizer_ = std::make_unique<Formula>(JSONObject(finalizer_data.GetObject()), finalize_inputs);
    }
    else {
      throw std::runtime_error("LWTNN finalizer must be a formula node");
    }

    nn_ = std::make_unique<const lwt::LightweightNeuralNetwork>(cfg.inputs, cfg.layers, cfg.outputs);
  } catch (const std::exception& ex) {
    throw std::runtime_error(
      std::string("Failed to parse LWTNN model from 'opaque' field: ") + ex.what()
    );
  }
}

double detail::LWTNNEvaluationContext::evaluate(const std::vector<Variable::Type>& values) const
{
  // TODO: thread_local?
  lwt::ValueMap input_map;

  for (const auto& [name, idx] : input_spec_) {
    if ( auto pval = std::get_if<double>(&values[idx]) ) {
      input_map[name] = *pval;
    }
    else if ( auto pval = std::get_if<int64_t>(&values[idx]) ) {
      input_map[name] = static_cast<double>(*pval);
    }
    else {
      throw std::runtime_error("LWTNN input " + name + " has non-numeric type");
    }
  }

  const auto output_map = nn_->compute(input_map);

  std::vector<Variable::Type> finalizer_inputs;
  finalizer_inputs.reserve(output_names_.size());
  for (const auto& name : output_names_) {
    const auto it = output_map.find(name);
    if ( it == output_map.end() ) {
      throw std::runtime_error("LWTNN output missing expected key: " + name);
    }
    finalizer_inputs.emplace_back(it->second);
  }

  return finalizer_->evaluate(finalizer_inputs);
}

LWTNN::LWTNN(const JSONObject& json, const Correction& context) :
  model_(std::make_unique<const detail::LWTNNEvaluationContext>(json, context))
{}

LWTNN::~LWTNN() = default;
LWTNN::LWTNN(LWTNN&&) = default;
LWTNN& LWTNN::operator=(LWTNN&&) = default;

double LWTNN::evaluate(const std::vector<Variable::Type>& values) const {
  return model_->evaluate(values);
}
