#include "system/Logger.h"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>

#include "system/StringUtils.h"

namespace jarvis::system {

std::mutex Logger::mutex_;
std::wstring Logger::path_;

void Logger::Initialize(const std::wstring& path) {
    std::lock_guard lock(mutex_);
    path_ = path;
    std::filesystem::create_directories(std::filesystem::path(path_).parent_path());
}

void Logger::Info(const std::wstring& message) {
    Write(L"INFO", message);
}

void Logger::Warn(const std::wstring& message) {
    Write(L"WARN", message);
}

void Logger::Error(const std::wstring& message) {
    Write(L"ERROR", message);
}

void Logger::Write(const wchar_t* level, const std::wstring& message) {
    std::lock_guard lock(mutex_);
    if (path_.empty()) {
        return;
    }

    const auto now = std::chrono::system_clock::now();
    const std::time_t time = std::chrono::system_clock::to_time_t(now);
    std::tm localTime{};
    localtime_s(&localTime, &time);

    std::wstringstream line;
    line << std::put_time(&localTime, L"%Y-%m-%d %H:%M:%S") << L" [" << level << L"] " << message << L"\n";

    std::ofstream file(std::filesystem::path(path_), std::ios::binary | std::ios::app);
    const auto utf8 = WideToUtf8(line.str());
    file.write(utf8.data(), static_cast<std::streamsize>(utf8.size()));
}

}  // namespace system
