#pragma once

#include <atomic>
#include <chrono>
#include <filesystem>
#include <functional>
#include <string>
#include <thread>

namespace jarvis::system {

class ConfigWatcher {
public:
    explicit ConfigWatcher(std::wstring path);
    ~ConfigWatcher();

    void Start(std::function<void()> onChanged);
    void Stop();

private:
    std::wstring path_;
    std::function<void()> onChanged_;
    std::thread thread_;
    std::atomic_bool running_{false};
    std::filesystem::file_time_type lastWrite_{};
};

}  // namespace system
