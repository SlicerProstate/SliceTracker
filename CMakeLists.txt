cmake_minimum_required(VERSION 2.8.9)

project(Registration)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "http://www.example.com/Slicer/Extensions/Registration")
set(EXTENSION_CATEGORY "Examples")
set(EXTENSION_CONTRIBUTORS "Peter Behringer (SPL), Andriy Fedorov (SPL)")
set(EXTENSION_DESCRIPTION "This extension provides an easy to use registration interface for image, target and mask selection. Registration results are visible step-wise. ")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/Registration.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/Registration/Screenshots/1.png")

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(RegistrationModule)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_CPACK})
