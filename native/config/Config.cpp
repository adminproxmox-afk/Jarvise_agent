#include "config/Config.h"

#include <fstream>
#include <filesystem>
#include <sstream>

#include "config/JsonValue.h"
#include "system/StringUtils.h"

namespace jarvis::config {

namespace {

std::wstring ReadUtf8File(const std::wstring& path) {
    std::ifstream file(std::filesystem::path(path), std::ios::binary);
    if (!file) {
        throw JsonError("Unable to open config file.");
    }
    std::stringstream buffer;
    buffer << file.rdbuf();
    return jarvis::system::Utf8ToWide(buffer.str());
}

std::vector<std::wstring> ReadStringArray(const JsonValue& value) {
    std::vector<std::wstring> result;
    if (!value.IsArray()) {
        return result;
    }
    for (const auto& item : value.AsArray()) {
        if (item.IsString()) {
            result.push_back(item.AsString());
        }
    }
    return result;
}

AppLaunchConfig ReadApp(const JsonValue& root, const std::wstring& key, AppLaunchConfig defaults) {
    const auto& value = root.Get(key);
    if (!value.IsObject()) {
        return defaults;
    }
    defaults.id = key;
    defaults.enabled = value.Get(L"enabled").AsBool(defaults.enabled);
    defaults.processName = value.Get(L"process_name").AsString(defaults.processName);
    defaults.command = value.Get(L"command").AsString(defaults.command);
    defaults.skipIfRunning = value.Get(L"skip_if_running").AsBool(defaults.skipIfRunning);
    defaults.pathCandidates = ReadStringArray(value.Get(L"path_candidates"));
    return defaults;
}

}  // namespace

AppConfig LoadConfig(const std::wstring& path) {
    const JsonValue json = ParseJson(ReadUtf8File(path));
    AppConfig config;

    const auto& assistant = json.Get(L"assistant");
    config.assistant.name = assistant.Get(L"name").AsString(config.assistant.name);
    config.assistant.startHidden = assistant.Get(L"start_hidden").AsBool(config.assistant.startHidden);
    config.assistant.enableAutorun = assistant.Get(L"enable_autorun").AsBool(config.assistant.enableAutorun);

    const auto& clap = json.Get(L"clap");
    config.clap.enabled = clap.Get(L"enabled").AsBool(config.clap.enabled);
    config.clap.sensitivity = clap.Get(L"sensitivity").AsNumber(config.clap.sensitivity);
    config.clap.doubleClapWindowMs = clap.Get(L"double_clap_window_ms").AsInt(config.clap.doubleClapWindowMs);
    config.clap.minClapGapMs = clap.Get(L"min_clap_gap_ms").AsInt(config.clap.minClapGapMs);
    config.clap.cooldownMs = clap.Get(L"cooldown_ms").AsInt(config.clap.cooldownMs);
    config.clap.noiseFloorMultiplier = clap.Get(L"noise_floor_multiplier").AsNumber(config.clap.noiseFloorMultiplier);
    config.clap.adaptiveNoise = clap.Get(L"adaptive_noise").AsBool(config.clap.adaptiveNoise);

    const auto& startup = json.Get(L"startup");
    config.startup.soundPath = startup.Get(L"sound_path").AsString(config.startup.soundPath);
    config.startup.overlayDurationMs = startup.Get(L"overlay_duration_ms").AsInt(config.startup.overlayDurationMs);

    const auto& spotify = json.Get(L"spotify");
    config.spotify.enabled = spotify.Get(L"enabled").AsBool(config.spotify.enabled);
    config.spotify.processName = spotify.Get(L"process_name").AsString(config.spotify.processName);
    config.spotify.launchUri = spotify.Get(L"launch_uri").AsString(config.spotify.launchUri);
    config.spotify.trackUri = spotify.Get(L"track_uri").AsString(config.spotify.trackUri);
    config.spotify.trackName = spotify.Get(L"track_name").AsString(config.spotify.trackName);
    config.spotify.sendMediaPlayKey = spotify.Get(L"send_media_play_key").AsBool(config.spotify.sendMediaPlayKey);
    config.spotify.startupDelayMs = spotify.Get(L"startup_delay_ms").AsInt(config.spotify.startupDelayMs);

    const auto& workspace = json.Get(L"workspace");
    config.workspace.chrome = ReadApp(workspace, L"chrome", {true, L"chrome", L"chrome.exe", L"chrome.exe", true, {}});
    config.workspace.ayugram = ReadApp(workspace, L"ayugram", {true, L"ayugram", L"AyuGram.exe", L"C:\\AG\\AyuGram.exe", true, {}});
    config.workspace.vscode = ReadApp(workspace, L"vscode", {true, L"vscode", L"Code.exe", L"code.exe", true, {}});
    config.workspace.androidStudio = ReadApp(workspace, L"android_studio", {true, L"android_studio", L"studio64.exe", L"studio64.exe", true, {}});

    const auto& ui = json.Get(L"ui");
    config.ui.opacity = ui.Get(L"opacity").AsNumber(config.ui.opacity);
    config.ui.accent = ui.Get(L"accent").AsString(config.ui.accent);
    config.ui.warmAccent = ui.Get(L"warm_accent").AsString(config.ui.warmAccent);

    const auto& logging = json.Get(L"logging");
    config.logging.path = logging.Get(L"path").AsString(config.logging.path);

    return config;
}

}  // namespace jarvis::config
