# MEMBRA LLMGPT — Makefile (C++)
# Build with: make
# Clean: make clean
# Release: make release

CXX := g++
CXXFLAGS := -std=c++17 -Wall -Wextra -Iinclude
LDFLAGS :=

# OpenMP — disabled by default (Apple Clang lacks support)
# To enable: make OPENMP=1
ifeq ($(OPENMP),1)
	CXXFLAGS += -fopenmp
	LDFLAGS += -fopenmp
endif

# Source files
SRC := src/gpt.cpp src/main.cpp
OBJ := $(SRC:.cpp=.o)
TARGET := llmgpt

# Default: debug build
.PHONY: all clean release install

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CXX) $(OBJ) -o $@ $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

# Release build with optimizations
release: CXXFLAGS += -O3 -march=native -ffast-math -DNDEBUG
release: clean $(TARGET)

# macOS specific (Apple Clang)
macos:
	$(MAKE) CXX=clang++ CXXFLAGS="-std=c++17 -Wall -Wextra -Iinclude -O3 -march=native" LDFLAGS=""

# Clean build artifacts
clean:
	rm -f $(OBJ) $(TARGET)

# Install to /usr/local
install: $(TARGET)
	cp $(TARGET) /usr/local/bin/
	mkdir -p /usr/local/include/llmgpt
	cp include/*.hpp /usr/local/include/llmgpt/

# Run chat mode
chat: $(TARGET)
	./$(TARGET) chat

# Run info
info: $(TARGET)
	./$(TARGET) info

# Quick inference test
test: $(TARGET)
	./$(TARGET) infer "Hello world"
