#include "system/StringUtils.h"

#include <algorithm>
#include <cwctype>
#include <vector>

#include <windows.h>

#include "system/ProcessUtils.h"

namespace jarvis::system {

std::string WideToUtf8(const std::wstring& value) {
    if (value.empty()) {
        return {};
    }
    const int length = WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, nullptr, 0, nullptr, nullptr);
    std::string result(static_cast<size_t>(length - 1), '\0');
    WideCharToMultiByte(CP_UTF8, 0, value.c_str(), -1, result.data(), length, nullptr, nullptr);
    return result;
}

std::wstring Utf8ToWide(const std::string& value) {
    if (value.empty()) {
        return {};
    }
    const int length = MultiByteToWideChar(CP_UTF8, 0, value.c_str(), -1, nullptr, 0);
    std::wstring result(static_cast<size_t>(length - 1), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, value.c_str(), -1, result.data(), length);
    return result;
}

std::wstring ExpandEnvironmentStringsSafe(const std::wstring& value) {
    if (value.empty()) {
        return {};
    }
    const DWORD needed = ExpandEnvironmentStringsW(value.c_str(), nullptr, 0);
    if (needed == 0) {
        return value;
    }
    std::wstring result(needed, L'\0');
    ExpandEnvironmentStringsW(value.c_str(), result.data(), needed);
    if (!result.empty() && result.back() == L'\0') {
        result.pop_back();
    }
    return result;
}

std::wstring ResolvePathRelativeToExe(const std::wstring& path) {
    if (path.empty()) {
        return path;
    }
    const std::wstring expanded = ExpandEnvironmentStringsSafe(path);
    if (expanded.size() > 2 && expanded[1] == L':') {
        return expanded;
    }
    if (expanded.starts_with(L"\\\\") || expanded.starts_with(L"/")) {
        return expanded;
    }
    return ProcessUtils::ExecutableDirectory() + L"\\" + expanded;
}

std::wstring ToLower(std::wstring value) {
    std::ranges::transform(value, value.begin(), [](wchar_t ch) {
        return static_cast<wchar_t>(std::towlower(ch));
    });
    return value;
}

std::wstring Trim(std::wstring value) {
    const auto isSpace = [](wchar_t ch) { return std::iswspace(ch) != 0; };
    value.erase(value.begin(), std::find_if_not(value.begin(), value.end(), isSpace));
    value.erase(std::find_if_not(value.rbegin(), value.rend(), isSpace).base(), value.end());
    return value;
}

}  // namespace system
