#include "correction_detail.h"

using namespace correction;

template<>
std::string_view JSONObject::getRequired<std::string_view>(const char * key) const
{
  const auto it = json_.FindMember(key);
  if ( it != json_.MemberEnd() ) {
    if ( it->value.IsString() ) {
      return std::string_view(it->value.GetString(), it->value.GetStringLength());
    } else {
      throw std::runtime_error(
          "Encountered invalid type for required attribute '"
          + std::string(key) + "'");
    }
  }
  throw std::runtime_error(
      "Object missing required attribute '"
      + std::string(key) + "'");
}

size_t detail::find_input_index(const std::string_view name, const std::vector<Variable> &inputs) {
  size_t idx = 0;
  for (const auto& var : inputs) {
    if ( name == var.name() ) return idx;
    idx++;
  }
  throw std::runtime_error("Error: could not find variable " + std::string(name) + " in inputs");
}
