#include "system/SingleInstance.h"

namespace jarvis::system {

SingleInstance::SingleInstance(const std::wstring& mutexName) {
    mutex_ = CreateMutexW(nullptr, TRUE, mutexName.c_str());
    owner_ = mutex_ != nullptr && GetLastError() != ERROR_ALREADY_EXISTS;
}

SingleInstance::~SingleInstance() {
    if (mutex_) {
        if (owner_) {
            ReleaseMutex(mutex_);
        }
        CloseHandle(mutex_);
    }
}

}  // namespace system
