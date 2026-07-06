cmake_minimum_required(VERSION 3.24)

project(JarvisNative VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(JARVIS WIN32
    main.cpp
    audio/WasapiCapture.cpp
    clap_detection/ClapDetector.cpp
    config/Config.cpp
    config/JsonValue.cpp
    launcher/WorkspaceLauncher.cpp
    spotify/SpotifyController.cpp
    system/AutoRun.cpp
    system/ConfigWatcher.cpp
    system/Logger.cpp
    system/ProcessUtils.cpp
    system/SingleInstance.cpp
    system/StartupSound.cpp
    system/StringUtils.cpp
    system/TrayIcon.cpp
    ui/OverlayWindow.cpp
)

target_include_directories(JARVIS PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}
)

target_compile_definitions(JARVIS PRIVATE
    UNICODE
    _UNICODE
    NOMINMAX
    WIN32_LEAN_AND_MEAN
)

target_link_libraries(JARVIS PRIVATE
    ole32
    avrt
    winmm
    shell32
    shlwapi
    gdiplus
    dwmapi
)

if(MSVC)
    target_compile_options(JARVIS PRIVATE /W4 /permissive- /EHsc)
endif()

add_custom_command(TARGET JARVIS POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E make_directory "$<TARGET_FILE_DIR:JARVIS>/config"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_CURRENT_SOURCE_DIR}/config/config.json"
        "$<TARGET_FILE_DIR:JARVIS>/config/config.json"
)
