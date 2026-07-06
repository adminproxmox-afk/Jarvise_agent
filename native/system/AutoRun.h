#pragma once

#include <string>

namespace jarvis::system {

class AutoRun {
public:
    static bool Install(const std::wstring& appName, const std::wstring& executablePath);
    static bool Remove(const std::wstring& appName);
};

}  // namespace system
