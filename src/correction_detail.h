/*
  * correction_detail.h
  *
  *  Created on: Mar 17, 2024
  *
  * Utility functions and classes for use in private correctionlib implementation. Not intended for public use.
*/
#ifndef CORRECTIONLIB_DETAIL_H
#define CORRECTIONLIB_DETAIL_H
#include <rapidjson/document.h>
#include <stdexcept>
#include <optional>
#include <string_view>
#include "correction.h"

namespace correction {

class JSONObject {
  public:
    JSONObject(rapidjson::Value::ConstObject&& json) : json_(json) { }
    // necessary to force use of const Value::GetObject() method
    // must check if json is an object in calling code!
    JSONObject(const rapidjson::Document& json) : json_(json.GetObject()) { }

    template<typename T>
    T getRequired(const char * key) const {
      const auto it = json_.FindMember(key);
      if ( it != json_.MemberEnd() ) {
        if ( it->value.template Is<T>() ) {
          return it->value.template Get<T>();
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

    const rapidjson::Value& getRequiredValue(const char * key) const {
      const auto it = json_.FindMember(key);
      if ( it != json_.MemberEnd() ) {
        return it->value;
      }
      throw std::runtime_error(
          "Object missing required attribute '"
          + std::string(key) + "'");
    }

    template<typename T>
    std::optional<T> getOptional(const char * key) const {
      const auto it = json_.FindMember(key);
      if ( it != json_.MemberEnd() ) {
        if ( it->value.template Is<T>() ) {
          return it->value.template Get<T>();
        } else if ( it->value.IsNull() ) {
          return std::nullopt;
        } else {
          throw std::runtime_error(
              "Encountered invalid type for optional attribute '"
              + std::string(key) + "'");
        }
      }
      return std::nullopt;
    }

    // escape hatch
    inline auto FindMember(const char * key) const { return json_.FindMember(key); }
    inline auto MemberEnd() const { return json_.MemberEnd(); }

  private:
    rapidjson::Value::ConstObject json_;
};

// specialization for string_view as rapidjson only provides const char*
template<>
std::string_view JSONObject::getRequired<std::string_view>(const char*) const;


namespace detail {
  size_t find_input_index(const std::string_view name, const std::vector<Variable> &inputs);
}

} // namespace correction

#endif
