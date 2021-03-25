cmake_minimum_required(VERSION 3.11)

project(correctionlib LANGUAGES CXX)

set(PKG_INSTALL "correctionlib") ## python package name

include(FetchContent)
FetchContent_Declare(pybind11
  SOURCE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/pybind11
  CMAKE_ARGS "-DBUILD_TESTING=OFF -DPYBIND11_NOPYTHON=ON"
  )
FetchContent_MakeAvailable(pybind11)


add_library(correctionlib SHARED src/correction.cc src/formula_ast.cc)
set_target_properties(correctionlib PROPERTIES PUBLIC_HEADER include/correction.h)
target_include_directories(correctionlib
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:${PKG_INSTALL}/include>
  PRIVATE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/rapidjson/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/pybind11/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/cpp-peglib>
  )
target_compile_features(correctionlib PUBLIC cxx_std_17)
install(TARGETS correctionlib
  EXPORT correctionlib-targets
  LIBRARY DESTINATION ${PKG_INSTALL}/lib
  PUBLIC_HEADER DESTINATION ${PKG_INSTALL}/include
  )


pybind11_add_module(_core MODULE src/python.cc)
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


install(EXPORT correctionlib-targets FILE correctionlib-targets.cmake DESTINATION ${PKG_INSTALL}/cmake)
include(CMakePackageConfigHelpers)
configure_package_config_file(${CMAKE_CURRENT_SOURCE_DIR}/Config.cmake.in
  "${CMAKE_CURRENT_BINARY_DIR}/correctionlibConfig.cmake"
  INSTALL_DESTINATION "${PKG_INSTALL}/cmake"
  NO_SET_AND_CHECK_MACRO NO_CHECK_REQUIRED_COMPONENTS_MACRO
  )
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/correctionlibConfigVersion.cmake"
  VERSION "${Tutorial_VERSION_MAJOR}.${Tutorial_VERSION_MINOR}"
  COMPATIBILITY AnyNewerVersion
  )
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/correctionlibConfig.cmake DESTINATION ${PKG_INSTALL}/cmake)