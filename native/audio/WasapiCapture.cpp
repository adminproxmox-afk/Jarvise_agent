#include "audio/WasapiCapture.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>

#include <audioclient.h>
#include <avrt.h>
#include <ksmedia.h>
#include <mmdeviceapi.h>
#include <windows.h>

#include "system/Logger.h"

namespace jarvis::audio {

namespace {

template <typename T>
struct ComReleaser {
    void operator()(T* value) const {
        if (value) {
            value->Release();
        }
    }
};

template <typename T>
using ComPtr = std::unique_ptr<T, ComReleaser<T>>;

bool IsFloatFormat(const WAVEFORMATEX* format) {
    if (format->wFormatTag == WAVE_FORMAT_IEEE_FLOAT) {
        return true;
    }
    if (format->wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
        const auto* extensible = reinterpret_cast<const WAVEFORMATEXTENSIBLE*>(format);
        return IsEqualGUID(extensible->SubFormat, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT);
    }
    return false;
}

bool IsPcm16Format(const WAVEFORMATEX* format) {
    if (format->wFormatTag == WAVE_FORMAT_PCM && format->wBitsPerSample == 16) {
        return true;
    }
    if (format->wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
        const auto* extensible = reinterpret_cast<const WAVEFORMATEXTENSIBLE*>(format);
        return IsEqualGUID(extensible->SubFormat, KSDATAFORMAT_SUBTYPE_PCM) && format->wBitsPerSample == 16;
    }
    return false;
}

}  // namespace

WasapiCapture::~WasapiCapture() {
    Stop();
}

bool WasapiCapture::Start(Callback callback) {
    if (running_.exchange(true)) {
        return true;
    }
    callback_ = std::move(callback);
    thread_ = std::thread([this] { CaptureThread(); });
    return true;
}

void WasapiCapture::Stop() {
    if (!running_.exchange(false)) {
        return;
    }
    if (thread_.joinable()) {
        thread_.join();
    }
}

void WasapiCapture::CaptureThread() {
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool comInitialized = SUCCEEDED(hr);

    IMMDeviceEnumerator* enumeratorRaw = nullptr;
    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, IID_PPV_ARGS(&enumeratorRaw));
    if (FAILED(hr)) {
        jarvis::system::Logger::Error(L"Failed to create MMDeviceEnumerator.");
        running_ = false;
        if (comInitialized) {
            CoUninitialize();
        }
        return;
    }
    ComPtr<IMMDeviceEnumerator> enumerator(enumeratorRaw);

    IMMDevice* deviceRaw = nullptr;
    hr = enumerator->GetDefaultAudioEndpoint(eCapture, eConsole, &deviceRaw);
    if (FAILED(hr)) {
        jarvis::system::Logger::Error(L"Default microphone endpoint not available.");
        running_ = false;
        if (comInitialized) {
            CoUninitialize();
        }
        return;
    }
    ComPtr<IMMDevice> device(deviceRaw);

    IAudioClient* audioClientRaw = nullptr;
    hr = device->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, reinterpret_cast<void**>(&audioClientRaw));
    if (FAILED(hr)) {
        jarvis::system::Logger::Error(L"Failed to activate IAudioClient.");
        running_ = false;
        if (comInitialized) {
            CoUninitialize();
        }
        return;
    }
    ComPtr<IAudioClient> audioClient(audioClientRaw);

    WAVEFORMATEX* mixFormat = nullptr;
    hr = audioClient->GetMixFormat(&mixFormat);
    if (FAILED(hr) || mixFormat == nullptr) {
        jarvis::system::Logger::Error(L"Failed to read microphone mix format.");
        running_ = false;
        if (comInitialized) {
            CoUninitialize();
        }
        return;
    }

    constexpr REFERENCE_TIME bufferDuration = 1000000;  // 100 ms.
    hr = audioClient->Initialize(AUDCLNT_SHAREMODE_SHARED, 0, bufferDuration, 0, mixFormat, nullptr);
    if (FAILED(hr)) {
        CoTaskMemFree(mixFormat);
        jarvis::system::Logger::Error(L"Failed to initialize WASAPI capture client.");
        running_ = false;
        if (comInitialized) {
            CoUninitialize();
        }
        return;
    }

    IAudioCaptureClient* captureClientRaw = nullptr;
    hr = audioClient->GetService(IID_PPV_ARGS(&captureClientRaw));
    if (FAILED(hr)) {
        CoTaskMemFree(mixFormat);
        jarvis::system::Logger::Error(L"Failed to get IAudioCaptureClient.");
        running_ = false;
        if (comInitialized) {
            CoUninitialize();
        }
        return;
    }
    ComPtr<IAudioCaptureClient> captureClient(captureClientRaw);

    DWORD taskIndex = 0;
    HANDLE avrtHandle = AvSetMmThreadCharacteristicsW(L"Audio", &taskIndex);

    hr = audioClient->Start();
    if (FAILED(hr)) {
        CoTaskMemFree(mixFormat);
        jarvis::system::Logger::Error(L"Failed to start WASAPI capture.");
        running_ = false;
        if (avrtHandle) {
            AvRevertMmThreadCharacteristics(avrtHandle);
        }
        if (comInitialized) {
            CoUninitialize();
        }
        return;
    }

    const bool floatFormat = IsFloatFormat(mixFormat);
    const bool pcm16Format = IsPcm16Format(mixFormat);
    const WORD channels = std::max<WORD>(1, mixFormat->nChannels);
    const int sampleRate = static_cast<int>(mixFormat->nSamplesPerSec);

    while (running_) {
        UINT32 packetFrames = 0;
        hr = captureClient->GetNextPacketSize(&packetFrames);
        if (FAILED(hr)) {
            break;
        }

        while (packetFrames > 0) {
            BYTE* data = nullptr;
            UINT32 frames = 0;
            DWORD flags = 0;
            hr = captureClient->GetBuffer(&data, &frames, &flags, nullptr, nullptr);
            if (FAILED(hr)) {
                running_ = false;
                break;
            }

            AudioChunk chunk;
            chunk.sampleRate = sampleRate;
            chunk.samples.resize(frames);

            if ((flags & AUDCLNT_BUFFERFLAGS_SILENT) != 0) {
                std::ranges::fill(chunk.samples, 0.0f);
            } else if (floatFormat) {
                const auto* samples = reinterpret_cast<const float*>(data);
                for (UINT32 frame = 0; frame < frames; ++frame) {
                    float sum = 0.0f;
                    for (WORD channel = 0; channel < channels; ++channel) {
                        sum += samples[frame * channels + channel];
                    }
                    chunk.samples[frame] = sum / static_cast<float>(channels);
                }
            } else if (pcm16Format) {
                const auto* samples = reinterpret_cast<const int16_t*>(data);
                for (UINT32 frame = 0; frame < frames; ++frame) {
                    float sum = 0.0f;
                    for (WORD channel = 0; channel < channels; ++channel) {
                        sum += static_cast<float>(samples[frame * channels + channel]) / 32768.0f;
                    }
                    chunk.samples[frame] = sum / static_cast<float>(channels);
                }
            }

            captureClient->ReleaseBuffer(frames);
            if (callback_ && !chunk.samples.empty()) {
                callback_(chunk);
            }

            hr = captureClient->GetNextPacketSize(&packetFrames);
            if (FAILED(hr)) {
                running_ = false;
                break;
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(8));
    }

    audioClient->Stop();
    CoTaskMemFree(mixFormat);
    if (avrtHandle) {
        AvRevertMmThreadCharacteristics(avrtHandle);
    }
    if (comInitialized) {
        CoUninitialize();
    }
}

}  // namespace jarvis::audio
