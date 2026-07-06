#pragma once

#include <string>

#include <windows.h>

namespace jarvis::system {

class SingleInstance {
public:
    explicit SingleInstance(const std::wstring& mutexName);
    ~SingleInstance();

    SingleInstance(const SingleInstance&) = delete;
    SingleInstance& operator=(const SingleInstance&) = delete;

    bool IsOwner() const { return owner_; }

private:
    HANDLE mutex_{nullptr};
    bool owner_{false};
};

}  // namespace system
