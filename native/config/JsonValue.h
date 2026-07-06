#pragma once

#include <map>
#include <stdexcept>
#include <string>
#include <variant>
#include <vector>

namespace jarvis::config {

class JsonError : public std::runtime_error {
public:
    explicit JsonError(const std::string& message) : std::runtime_error(message) {}
};

class JsonValue {
public:
    using Object = std::map<std::wstring, JsonValue>;
    using Array = std::vector<JsonValue>;
    using Storage = std::variant<std::nullptr_t, bool, double, std::wstring, Object, Array>;

    JsonValue() : value_(nullptr) {}
    explicit JsonValue(Storage value) : value_(std::move(value)) {}

    bool IsNull() const { return std::holds_alternative<std::nullptr_t>(value_); }
    bool IsBool() const { return std::holds_alternative<bool>(value_); }
    bool IsNumber() const { return std::holds_alternative<double>(value_); }
    bool IsString() const { return std::holds_alternative<std::wstring>(value_); }
    bool IsObject() const { return std::holds_alternative<Object>(value_); }
    bool IsArray() const { return std::holds_alternative<Array>(value_); }

    bool AsBool(bool fallback = false) const;
    double AsNumber(double fallback = 0.0) const;
    int AsInt(int fallback = 0) const;
    std::wstring AsString(std::wstring fallback = L"") const;

    const Object& AsObject() const;
    const Array& AsArray() const;

    const JsonValue& Get(const std::wstring& key) const;
    const JsonValue& Get(const std::wstring& key, const JsonValue& fallback) const;

private:
    Storage value_;
};

JsonValue ParseJson(const std::wstring& text);

}  // namespace jarvis::config
