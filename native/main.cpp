#include <atomic>
#include <memory>
#include <thread>

#include <windows.h>

#include "audio/WasapiCapture.h"
#include "clap_detection/ClapDetector.h"
#include "config/Config.h"
#include "launcher/WorkspaceLauncher.h"
#include "spotify/SpotifyController.h"
#include "system/AutoRun.h"
#include "system/ConfigWatcher.h"
#include "system/Logger.h"
#include "system/ProcessUtils.h"
#include "system/SingleInstance.h"
#include "system/StartupSound.h"
#include "system/StringUtils.h"
#include "ui/OverlayWindow.h"

namespace {

constexpr UINT WM_JARVIS_ACTIVATE = WM_APP + 101;

class JarvisRuntime {
public:
    explicit JarvisRuntime(HINSTANCE instance) : instance_(instance) {}

    int Run() {
        jarvis::system::SingleInstance singleInstance(L"JARVIS.Native.Assistant.Mutex");
        if (!singleInstance.IsOwner()) {
            MessageBoxW(nullptr, L"JARVIS is already running.", L"JARVIS", MB_OK | MB_ICONINFORMATION);
            return 0;
        }

        const auto exeDir = jarvis::system::ProcessUtils::ExecutableDirectory();
        SetCurrentDirectoryW(exeDir.c_str());

        configPath_ = exeDir + L"\\config\\config.json";
        config_ = std::make_shared<jarvis::config::AppConfig>(jarvis::config::LoadConfig(configPath_));

        jarvis::system::Logger::Initialize(jarvis::system::ResolvePathRelativeToExe(config_->logging.path));
        jarvis::system::Logger::Info(L"JARVIS native runtime booting.");

        if (config_->assistant.enableAutorun) {
            jarvis::system::AutoRun::Install(L"JARVIS", jarvis::system::ProcessUtils::ExecutablePath());
        }

        overlay_ = std::make_unique<jarvis::ui::OverlayWindow>(instance_);
        overlay_->SetActivationCallback([this] { RequestActivation(); });
        overlay_->SetReloadCallback([this] { ReloadConfig(); });
        overlay_->SetExitCallback([this] { Shutdown(); });

        if (!overlay_->Create(config_->assistant.name)) {
            jarvis::system::Logger::Error(L"Failed to create overlay window.");
            return 1;
        }

        overlay_->InstallTrayIcon(config_->assistant.name);

        clapDetector_ = std::make_unique<jarvis::clap_detection::ClapDetector>(config_->clap);
        clapDetector_->SetDoubleClapCallback([this] { RequestActivation(); });

        audio_ = std::make_unique<jarvis::audio::WasapiCapture>();
        if (config_->clap.enabled) {
            const bool audioStarted = audio_->Start([this](const jarvis::audio::AudioChunk& chunk) {
                clapDetector_->Process(chunk);
            });
            jarvis::system::Logger::Info(audioStarted ? L"WASAPI microphone capture started." : L"WASAPI microphone capture unavailable.");
        }

        watcher_ = std::make_unique<jarvis::system::ConfigWatcher>(configPath_);
        watcher_->Start([this] { ReloadConfig(); });

        MSG msg{};
        while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
            if (msg.message == WM_JARVIS_ACTIVATE) {
                Activate();
                continue;
            }
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }

        StopServices();
        jarvis::system::Logger::Info(L"JARVIS native runtime stopped.");
        return static_cast<int>(msg.wParam);
    }

private:
    void RequestActivation() {
        if (!overlay_) {
            return;
        }
        PostMessageW(overlay_->Handle(), WM_JARVIS_ACTIVATE, 0, 0);
    }

    void Activate() {
        if (activationInProgress_.exchange(true)) {
            jarvis::system::Logger::Info(L"Activation ignored because a previous sequence is still running.");
            return;
        }

        auto snapshot = config_;
        overlay_->ShowStartup(snapshot->startup.overlayDurationMs);

        std::thread([this, snapshot] {
            jarvis::system::Logger::Info(L"Double clap activation sequence started.");
            jarvis::system::StartupSound::Play(snapshot->startup.soundPath);

            jarvis::spotify::SpotifyController spotify(snapshot->spotify);
            jarvis::launcher::WorkspaceLauncher launcher(snapshot->workspace, spotify);
            launcher.LaunchAll();

            jarvis::system::Logger::Info(L"Workspace launch sequence completed.");
            activationInProgress_ = false;
        }).detach();
    }

    void ReloadConfig() {
        try {
            auto next = std::make_shared<jarvis::config::AppConfig>(jarvis::config::LoadConfig(configPath_));
            config_ = next;
            if (clapDetector_) {
                clapDetector_->UpdateSettings(next->clap);
            }
            jarvis::system::Logger::Info(L"Config reloaded.");
        } catch (const std::exception& ex) {
            jarvis::system::Logger::Error(L"Config reload failed: " + jarvis::system::Utf8ToWide(ex.what()));
        }
    }

    void Shutdown() {
        StopServices();
        PostQuitMessage(0);
    }

    void StopServices() {
        if (watcher_) {
            watcher_->Stop();
        }
        if (audio_) {
            audio_->Stop();
        }
        if (overlay_) {
            overlay_->RemoveTrayIcon();
        }
    }

    HINSTANCE instance_{};
    std::wstring configPath_;
    std::shared_ptr<jarvis::config::AppConfig> config_;
    std::unique_ptr<jarvis::audio::WasapiCapture> audio_;
    std::unique_ptr<jarvis::clap_detection::ClapDetector> clapDetector_;
    std::unique_ptr<jarvis::ui::OverlayWindow> overlay_;
    std::unique_ptr<jarvis::system::ConfigWatcher> watcher_;
    std::atomic_bool activationInProgress_{false};
};

}  // namespace

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE, PWSTR, int) {
    JarvisRuntime runtime(instance);
    return runtime.Run();
}
