#include "system/StartupSound.h"

#include <filesystem>

#include <windows.h>
#include <mmsystem.h>

#include "system/StringUtils.h"

namespace jarvis::system {

void StartupSound::Play(const std::wstring& soundPath) {
    const auto resolved = ResolvePathRelativeToExe(soundPath);
    if (!resolved.empty() && std::filesystem::exists(resolved)) {
        PlaySoundW(resolved.c_str(), nullptr, SND_FILENAME | SND_ASYNC);
        return;
    }

    Beep(523, 75);
    Beep(784, 95);
    Beep(1046, 135);
    Beep(1568, 180);
}

}  // namespace system
