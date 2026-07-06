#pragma once

#include <string>
#include <vector>

namespace jarvis::config {

struct AssistantConfig {
    std::wstring name = L"JARVIS";
    bool startHidden = true;
    bool enableAutorun = true;
};

struct ClapConfig {
    bool enabled = true;
    double sensitivity = 0.18;
    int doubleClapWindowMs = 650;
    int minClapGapMs = 140;
    int cooldownMs = 2800;
    double noiseFloorMultiplier = 4.4;
    bool adaptiveNoise = true;
};

struct StartupConfig {
    std::wstring soundPath;
    int overlayDurationMs = 5200;
};

struct SpotifyConfig {
    bool enabled = true;
    std::wstring processName = L"Spotify.exe";
    std::wstring launchUri = L"spotify:";
    std::wstring trackUri = L"spotify:track:39shmbIHICJ2Wxnk1fPSdz";
    std::wstring trackName = L"The Clash - Should I Stay or Should I Go";
    bool sendMediaPlayKey = true;
    int startupDelayMs = 1600;
};

struct AppLaunchConfig {
    bool enabled = true;
    std::wstring id;
    std::wstring processName;
    std::wstring command;
    bool skipIfRunning = true;
    std::vector<std::wstring> pathCandidates;
};

struct WorkspaceConfig {
    AppLaunchConfig chrome;
    AppLaunchConfig ayugram;
    AppLaunchConfig vscode;
    AppLaunchConfig androidStudio;
};

struct UiConfig {
    double opacity = 0.88;
    std::wstring accent = L"#36E8FF";
    std::wstring warmAccent = L"#FFD166";
};

struct LoggingConfig {
    std::wstring path = L"logs\\jarvis-native.log";
};

struct AppConfig {
    AssistantConfig assistant;
    ClapConfig clap;
    StartupConfig startup;
    SpotifyConfig spotify;
    WorkspaceConfig workspace;
    UiConfig ui;
    LoggingConfig logging;
};

AppConfig LoadConfig(const std::wstring& path);

}  // namespace jarvis::config
