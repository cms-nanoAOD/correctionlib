cmake_minimum_required(VERSION 3.11)

if(NOT SKBUILD_PROJECT_VERSION)
  set(SKBUILD_PROJECT_VERSION "0.0.0")  # provided by scikit-build-core
endif()
string(REPLACE "." ";" VERSION_SPLIT ${SKBUILD_PROJECT_VERSION})
list(GET VERSION_SPLIT 0 SPLIT_VERSION_MAJOR)
list(GET VERSION_SPLIT 1 SPLIT_VERSION_MINOR)

project(correctionlib VERSION ${SPLIT_VERSION_MAJOR}.${SPLIT_VERSION_MINOR} LANGUAGES CXX)

option(BUILD_DEMO "Build demo program" ON)

set(PKG_INSTALL "correctionlib") ## python package name

include(FetchContent)
FetchContent_Declare(pybind11
  SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/pybind11
  CMAKE_ARGS "-DBUILD_TESTING=OFF -DPYBIND11_NOPYTHON=ON"
  )
FetchContent_MakeAvailable(pybind11)

set(THREADS_PREFER_PTHREAD_FLAG ON)
find_package(Threads)
find_package(ZLIB)


configure_file(include/version.h.in ${CMAKE_CURRENT_BINARY_DIR}/include/correctionlib_version.h)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/include/correctionlib_version.h DESTINATION ${PKG_INSTALL}/include)


add_library(correctionlib SHARED src/correction.cc src/formula_ast.cc)
set_target_properties(correctionlib PROPERTIES PUBLIC_HEADER include/correction.h WINDOWS_EXPORT_ALL_SYMBOLS ON)
target_include_directories(correctionlib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/include>
    $<INSTALL_INTERFACE:${PKG_INSTALL}/include>
  PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/rapidjson/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/cpp-peglib>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/xxhash>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/pcg-cpp/include>
  )
target_compile_features(correctionlib PUBLIC cxx_std_17)
if(MSVC)
  target_compile_options(correctionlib PRIVATE /Zc:__cplusplus /utf-8)
else()
  target_compile_options(correctionlib PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
if(ZLIB_FOUND)
  target_link_libraries(correctionlib PRIVATE ZLIB::ZLIB)
endif()
if(Threads_FOUND AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  target_link_libraries(correctionlib PRIVATE Threads::Threads)
endif()
install(TARGETS correctionlib
  EXPORT correctionlib-targets
  LIBRARY DESTINATION ${PKG_INSTALL}/lib
  ARCHIVE DESTINATION ${PKG_INSTALL}/lib
  RUNTIME DESTINATION ${PKG_INSTALL}/lib
  PUBLIC_HEADER DESTINATION ${PKG_INSTALL}/include
  )


pybind11_add_module(_core MODULE src/python.cc)
if(MSVC)
  target_compile_options(_core PRIVATE /W4 /WX)
else()
  target_compile_options(_core PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()
target_link_libraries(_core PRIVATE correctionlib)
set_target_properties(_core PROPERTIES BUILD_WITH_INSTALL_RPATH ON)
if (APPLE)
  set_target_properties(_core PROPERTIES INSTALL_NAME_DIR "@rpath" )
  set_target_properties(_core PROPERTIES INSTALL_RPATH "@loader_path/lib" )
else (UNIX)
  set_target_properties(_core PROPERTIES INSTALL_RPATH "\$ORIGIN/lib" )
endif()
install(TARGETS _core LIBRARY DESTINATION ${PKG_INSTALL})


add_executable(demo src/demo.cc)
target_link_libraries(demo PRIVATE correctionlib)
if(NOT BUILD_DEMO)
  set_target_properties(demo PROPERTIES EXCLUDE_FROM_ALL ON)
endif()


install(EXPORT correctionlib-targets FILE correctionlib-targets.cmake DESTINATION ${PKG_INSTALL}/cmake)
include(CMakePackageConfigHelpers)
configure_package_config_file(${CMAKE_CURRENT_SOURCE_DIR}/Config.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/correctionlibConfig.cmake"
  INSTALL_DESTINATION "${PKG_INSTALL}/cmake"
  NO_SET_AND_CHECK_MACRO NO_CHECK_REQUIRED_COMPONENTS_MACRO
  )
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/correctionlibConfigVersion.cmake"
  VERSION "${correctionlib_VERSION_MAJOR}.${correctionlib_VERSION_MINOR}"
  COMPATIBILITY AnyNewerVersion
  )
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/correctionlibConfig.cmake ${CMAKE_CURRENT_BINARY_DIR}/correctionlibConfigVersion.cmake DESTINATION ${PKG_INSTALL}/cmake)
