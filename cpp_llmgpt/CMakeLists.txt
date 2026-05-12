cmake_minimum_required(VERSION 3.16)
project(LLMGPT VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# OpenMP for parallel matrix ops
find_package(OpenMP)

# Include directories
include_directories(${CMAKE_SOURCE_DIR}/include)

# Source files
set(SOURCES
    src/gpt.cpp
    src/main.cpp
)

# Main executable
add_executable(llmgpt ${SOURCES})

if(OpenMP_CXX_FOUND)
    target_link_libraries(llmgpt PUBLIC OpenMP::OpenMP_CXX)
    target_compile_options(llmgpt PUBLIC -fopenmp)
endif()

# Optimization flags
if(CMAKE_BUILD_TYPE STREQUAL "Release")
    if(CMAKE_CXX_COMPILER_ID STREQUAL "GNU" OR CMAKE_CXX_COMPILER_ID STREQUAL "Clang")
        target_compile_options(llmgpt PRIVATE -O3 -march=native -ffast-math)
    elseif(CMAKE_CXX_COMPILER_ID STREQUAL "AppleClang")
        target_compile_options(llmgpt PRIVATE -O3 -march=native)
    endif()
endif()

# Apple Silicon MPS hint (no direct MPS in pure C++, but flags help)
if(APPLE)
    target_compile_definitions(llmgpt PRIVATE APPLE_SILICON=1)
endif()

# Install
install(TARGETS llmgpt DESTINATION bin)
install(DIRECTORY include/ DESTINATION include)
