#include "config/JsonValue.h"

#include <cwctype>
#include <sstream>

namespace jarvis::config {

namespace {

const JsonValue kNull;

class Parser {
public:
    explicit Parser(std::wstring text) : text_(std::move(text)) {}

    JsonValue Parse() {
        SkipWhitespace();
        JsonValue value = ParseValue();
        SkipWhitespace();
        if (!AtEnd()) {
            Fail("Unexpected trailing content.");
        }
        return value;
    }

private:
    JsonValue ParseValue() {
        SkipWhitespace();
        if (AtEnd()) {
            Fail("Unexpected end of JSON.");
        }
        const wchar_t ch = Peek();
        if (ch == L'{') {
            return JsonValue(ParseObject());
        }
        if (ch == L'[') {
            return JsonValue(ParseArray());
        }
        if (ch == L'"') {
            return JsonValue(ParseString());
        }
        if (ch == L't' || ch == L'f') {
            return JsonValue(ParseBool());
        }
        if (ch == L'n') {
            ParseNull();
            return JsonValue();
        }
        if (ch == L'-' || std::iswdigit(ch)) {
            return JsonValue(ParseNumber());
        }
        Fail("Unexpected JSON token.");
    }

    JsonValue::Object ParseObject() {
        Expect(L'{');
        JsonValue::Object object;
        SkipWhitespace();
        if (TryConsume(L'}')) {
            return object;
        }

        while (true) {
            SkipWhitespace();
            if (Peek() != L'"') {
                Fail("Expected object key.");
            }
            std::wstring key = ParseString();
            SkipWhitespace();
            Expect(L':');
            object.emplace(std::move(key), ParseValue());
            SkipWhitespace();
            if (TryConsume(L'}')) {
                break;
            }
            Expect(L',');
        }
        return object;
    }

    JsonValue::Array ParseArray() {
        Expect(L'[');
        JsonValue::Array array;
        SkipWhitespace();
        if (TryConsume(L']')) {
            return array;
        }

        while (true) {
            array.push_back(ParseValue());
            SkipWhitespace();
            if (TryConsume(L']')) {
                break;
            }
            Expect(L',');
        }
        return array;
    }

    std::wstring ParseString() {
        Expect(L'"');
        std::wstring result;
        while (!AtEnd()) {
            const wchar_t ch = Advance();
            if (ch == L'"') {
                return result;
            }
            if (ch != L'\\') {
                result.push_back(ch);
                continue;
            }

            if (AtEnd()) {
                Fail("Unterminated escape sequence.");
            }
            const wchar_t escaped = Advance();
            switch (escaped) {
                case L'"': result.push_back(L'"'); break;
                case L'\\': result.push_back(L'\\'); break;
                case L'/': result.push_back(L'/'); break;
                case L'b': result.push_back(L'\b'); break;
                case L'f': result.push_back(L'\f'); break;
                case L'n': result.push_back(L'\n'); break;
                case L'r': result.push_back(L'\r'); break;
                case L't': result.push_back(L'\t'); break;
                case L'u': result.push_back(ParseUnicodeEscape()); break;
                default: Fail("Unsupported escape sequence.");
            }
        }
        Fail("Unterminated string.");
    }

    wchar_t ParseUnicodeEscape() {
        unsigned int value = 0;
        for (int i = 0; i < 4; ++i) {
            if (AtEnd()) {
                Fail("Incomplete unicode escape.");
            }
            const wchar_t ch = Advance();
            value <<= 4;
            if (ch >= L'0' && ch <= L'9') {
                value += ch - L'0';
            } else if (ch >= L'a' && ch <= L'f') {
                value += 10 + ch - L'a';
            } else if (ch >= L'A' && ch <= L'F') {
                value += 10 + ch - L'A';
            } else {
                Fail("Invalid unicode escape.");
            }
        }
        return static_cast<wchar_t>(value);
    }

    double ParseNumber() {
        const size_t start = index_;
        if (Peek() == L'-') {
            Advance();
        }
        while (!AtEnd() && std::iswdigit(Peek())) {
            Advance();
        }
        if (!AtEnd() && Peek() == L'.') {
            Advance();
            while (!AtEnd() && std::iswdigit(Peek())) {
                Advance();
            }
        }
        if (!AtEnd() && (Peek() == L'e' || Peek() == L'E')) {
            Advance();
            if (!AtEnd() && (Peek() == L'+' || Peek() == L'-')) {
                Advance();
            }
            while (!AtEnd() && std::iswdigit(Peek())) {
                Advance();
            }
        }
        return std::stod(text_.substr(start, index_ - start));
    }

    bool ParseBool() {
        if (Match(L"true")) {
            return true;
        }
        if (Match(L"false")) {
            return false;
        }
        Fail("Invalid boolean.");
    }

    void ParseNull() {
        if (!Match(L"null")) {
            Fail("Invalid null.");
        }
    }

    bool Match(const wchar_t* literal) {
        const std::wstring value(literal);
        if (text_.substr(index_, value.size()) != value) {
            return false;
        }
        index_ += value.size();
        return true;
    }

    void SkipWhitespace() {
        while (!AtEnd() && std::iswspace(Peek())) {
            ++index_;
        }
    }

    bool TryConsume(wchar_t expected) {
        if (!AtEnd() && Peek() == expected) {
            ++index_;
            return true;
        }
        return false;
    }

    void Expect(wchar_t expected) {
        if (AtEnd() || Peek() != expected) {
            std::ostringstream stream;
            stream << "Expected '" << static_cast<char>(expected) << "'.";
            Fail(stream.str());
        }
        ++index_;
    }

    wchar_t Peek() const { return text_[index_]; }
    wchar_t Advance() { return text_[index_++]; }
    bool AtEnd() const { return index_ >= text_.size(); }

    [[noreturn]] void Fail(const std::string& message) const {
        std::ostringstream stream;
        stream << message << " Offset: " << index_;
        throw JsonError(stream.str());
    }

    std::wstring text_;
    size_t index_{0};
};

}  // namespace

bool JsonValue::AsBool(bool fallback) const {
    return IsBool() ? std::get<bool>(value_) : fallback;
}

double JsonValue::AsNumber(double fallback) const {
    return IsNumber() ? std::get<double>(value_) : fallback;
}

int JsonValue::AsInt(int fallback) const {
    return IsNumber() ? static_cast<int>(std::get<double>(value_)) : fallback;
}

std::wstring JsonValue::AsString(std::wstring fallback) const {
    return IsString() ? std::get<std::wstring>(value_) : std::move(fallback);
}

const JsonValue::Object& JsonValue::AsObject() const {
    if (!IsObject()) {
        throw JsonError("JSON value is not an object.");
    }
    return std::get<Object>(value_);
}

const JsonValue::Array& JsonValue::AsArray() const {
    if (!IsArray()) {
        throw JsonError("JSON value is not an array.");
    }
    return std::get<Array>(value_);
}

const JsonValue& JsonValue::Get(const std::wstring& key) const {
    if (!IsObject()) {
        return kNull;
    }
    const auto& object = std::get<Object>(value_);
    const auto it = object.find(key);
    return it == object.end() ? kNull : it->second;
}

const JsonValue& JsonValue::Get(const std::wstring& key, const JsonValue& fallback) const {
    const auto& value = Get(key);
    return value.IsNull() ? fallback : value;
}

JsonValue ParseJson(const std::wstring& text) {
    return Parser(text).Parse();
}

}  // namespace jarvis::config
