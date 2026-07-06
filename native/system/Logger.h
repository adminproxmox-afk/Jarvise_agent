#pragma once

#include <mutex>
#include <string>

namespace jarvis::system {

class Logger {
public:
    static void Initialize(const std::wstring& path);
    static void Info(const std::wstring& message);
    static void Warn(const std::wstring& message);
    static void Error(const std::wstring& message);

private:
    static void Write(const wchar_t* level, const std::wstring& message);
    static std::mutex mutex_;
    static std::wstring path_;
};

}  // namespace system
