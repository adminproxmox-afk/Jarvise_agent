#include "system/ConfigWatcher.h"

#include "system/Logger.h"

namespace jarvis::system {

ConfigWatcher::ConfigWatcher(std::wstring path) : path_(std::move(path)) {}

ConfigWatcher::~ConfigWatcher() {
    Stop();
}

void ConfigWatcher::Start(std::function<void()> onChanged) {
    onChanged_ = std::move(onChanged);
    if (running_.exchange(true)) {
        return;
    }
    if (std::filesystem::exists(path_)) {
        lastWrite_ = std::filesystem::last_write_time(path_);
    }

    thread_ = std::thread([this] {
        while (running_) {
            std::this_thread::sleep_for(std::chrono::seconds(2));
            if (!std::filesystem::exists(path_)) {
                continue;
            }
            const auto current = std::filesystem::last_write_time(path_);
            if (current != lastWrite_) {
                lastWrite_ = current;
                Logger::Info(L"Config change detected.");
                if (onChanged_) {
                    onChanged_();
                }
            }
        }
    });
}

void ConfigWatcher::Stop() {
    if (!running_.exchange(false)) {
        return;
    }
    if (thread_.joinable()) {
        thread_.join();
    }
}

}  // namespace system
