cmake_minimum_required(VERSION 2.8.9)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_NAME SliceTracker)
set(EXTENSION_HOMEPAGE "https://github.com/SlicerProstate/SliceTracker")
set(EXTENSION_CATEGORY "IGT")
set(EXTENSION_CONTRIBUTORS "Christian Herz (SPL), Peter Behringer (SPL), Andriy Fedorov (SPL)")
set(EXTENSION_DESCRIPTION "This extension provides an easy to use registration interface for image, target and mask selection. Registration results are visible step-wise. ")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/Registration.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/Registration/Screenshots/1.png")

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

add_subdirectory(SliceTracker)
add_subdirectory(ZFrameCalibration)


#-----------------------------------------------------------------------------
if(BUILD_TESTING)

  # Register the unittest subclass in the main script as a ctest.
  # Note that the test will also be available at runtime.
  slicer_add_python_unittest(SCRIPT ${MODULE_NAME}.py)

  # Additional build-time testing
  add_subdirectory(Testing)
endif()

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_CPACK})
