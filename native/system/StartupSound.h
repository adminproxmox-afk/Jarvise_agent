#pragma once

#include <string>

namespace jarvis::system {

class StartupSound {
public:
    static void Play(const std::wstring& soundPath);
};

}  // namespace system
