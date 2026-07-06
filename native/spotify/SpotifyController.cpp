#include "spotify/SpotifyController.h"

#include <chrono>
#include <thread>
#include <utility>

#include <windows.h>

#include "system/Logger.h"
#include "system/ProcessUtils.h"

namespace jarvis::spotify {

namespace {
constexpr WORD kVkMediaPlay = 0xFA;
}

SpotifyController::SpotifyController(config::SpotifyConfig settings) : settings_(std::move(settings)) {}

bool SpotifyController::LaunchAndPlayTrack() {
    if (!settings_.enabled) {
        return true;
    }

    if (!jarvis::system::ProcessUtils::IsProcessRunning(settings_.processName)) {
        jarvis::system::ProcessUtils::LaunchUri(settings_.launchUri);
        std::this_thread::sleep_for(std::chrono::milliseconds(settings_.startupDelayMs));
    }

    jarvis::system::Logger::Info(L"Opening Spotify track: " + settings_.trackName);
    const bool opened = jarvis::system::ProcessUtils::LaunchUri(settings_.trackUri);
    std::this_thread::sleep_for(std::chrono::milliseconds(900));

    if (settings_.sendMediaPlayKey) {
        SendMediaPlayKey();
    }
    return opened;
}

void SpotifyController::SendMediaPlayKey() const {
    INPUT inputs[2]{};
    inputs[0].type = INPUT_KEYBOARD;
    inputs[0].ki.wVk = kVkMediaPlay;
    inputs[1].type = INPUT_KEYBOARD;
    inputs[1].ki.wVk = kVkMediaPlay;
    inputs[1].ki.dwFlags = KEYEVENTF_KEYUP;
    SendInput(2, inputs, sizeof(INPUT));
}

}  // namespace jarvis::spotify
