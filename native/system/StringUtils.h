#pragma once

#include <string>

namespace jarvis::system {

std::string WideToUtf8(const std::wstring& value);
std::wstring Utf8ToWide(const std::string& value);
std::wstring ExpandEnvironmentStringsSafe(const std::wstring& value);
std::wstring ResolvePathRelativeToExe(const std::wstring& path);
std::wstring ToLower(std::wstring value);
std::wstring Trim(std::wstring value);

}  // namespace system
