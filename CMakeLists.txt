cmake_minimum_required(VERSION 2.8.9)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_NAME SliceTracker)
set(EXTENSION_HOMEPAGE "http://www.example.com/Slicer/Extensions/Registration")
set(EXTENSION_CATEGORY "Radiology")
set(EXTENSION_CONTRIBUTORS "Peter Behringer (SPL), Christian Herz (SPL), Andriy Fedorov (SPL)")
set(EXTENSION_DESCRIPTION "This extension provides an easy to use registration interface for image, target and mask selection. Registration results are visible step-wise. ")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/Registration.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/Registration/Screenshots/1.png")

#-----------------------------------------------------------------------------
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
set(MODULE_NAME SliceTracker)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  SliceTrackerUtils/__init__.py
  SliceTrackerUtils/constants.py
  SliceTrackerUtils/exceptions.py
  SliceTrackerUtils/RegistrationData.py
  SliceTrackerUtils/ZFrameRegistration.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Colors/mpReviewColors.csv
  Resources/Icons/icon-cancelSegmentation.png
  Resources/Icons/icon-redo.png
  Resources/Icons/icon-undo.png
  Resources/Icons/icon-greenCheck.png
  Resources/Icons/icon-newImageData.png
  Resources/Icons/icon-quickSegmentation.png
  Resources/Icons/icon-settings.png
  Resources/Icons/icon-infoBox.png
  Resources/Icons/${MODULE_NAME}.png
  )

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )

slicerMacroBuildScriptedModule(
  NAME SliceTrackerRegistration
  SCRIPTS SliceTrackerRegistration.py
  RESOURCES ""
  WITH_GENERIC_TESTS
  )

slicerMacroBuildScriptedModule(
  NAME SliceTrackerZFrameRegistration
  SCRIPTS SliceTrackerZFrameRegistration.py
  RESOURCES ""
  WITH_GENERIC_TESTS
  )

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
