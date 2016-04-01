cmake_minimum_required(VERSION 2.8.7)

#set(CMAKE_MODULE_PATH ${CMAKE_MODULE_PATH} ${CMAKE_CURRENT_SOURCE_DIR}/../CMake)

#-----------------------------------------------------------------------------
# See http://cmake.org/cmake/help/cmake-2-8-docs.html#section_Policies for details
#-----------------------------------------------------------------------------

if(POLICY CMP0017)
  cmake_policy(SET CMP0017 OLD)
endif()
if(POLICY CMP0042)
  cmake_policy(SET CMP0042 NEW) # CMake 3.0.0
endif()

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_NAME ZFrameCalibration)
set(EXTENSION_HOMEPAGE "http://www.example.com/Slicer/Extensions/Registration")
set(EXTENSION_CATEGORY "Radiology")
set(EXTENSION_CONTRIBUTORS "")
set(EXTENSION_DESCRIPTION " ")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/Registration.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/Registration/Screenshots/1.png")

#-----------------------------------------------------------------------------
if(NOT Slicer_SOURCE_DIR)
  find_package(Slicer REQUIRED)
  include(${Slicer_USE_FILE})
endif()

#-----------------------------------------------------------------------------
set(MODULE_NAME ZFrameCalibration)

#-----------------------------------------------------------------------------
set(MODULE_INCLUDE_DIRECTORIES
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/
  ${CMAKE_CURRENT_SOURCE_DIR}/ZFrame/
  )

set(MODULE_SRCS
  ${CMAKE_CURRENT_SOURCE_DIR}/ZFrame/Calibration.h
  ${CMAKE_CURRENT_SOURCE_DIR}/ZFrame/Calibration.cxx
  ZFrameCalibration.cxx
  )

set(Newmat_SRCS
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat9.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmatrm.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/nm_misc.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/bandmat.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat1.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/solution.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/cholesky.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/hholder.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat2.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmatex.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat3.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/sort.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/evalue.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/jacobi.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat4.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/submat.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/example.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat5.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/svd.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/myexcept.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat6.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmatnl.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/fft.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat7.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newfft.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/newmat8.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/newmat/ZLinAlg.cxx
  )

set(MODULE_TARGET_LIBRARIES
  ${ITK_LIBRARIES}
  )

#-----------------------------------------------------------------------------
SEMMacroBuildCLI(
  NAME ${MODULE_NAME}
  TARGET_LIBRARIES ${MODULE_TARGET_LIBRARIES}
  INCLUDE_DIRECTORIES ${MODULE_INCLUDE_DIRECTORIES}
  ADDITIONAL_SRCS ${MODULE_SRCS} ${Newmat_SRCS}
  #EXECUTABLE_ONLY
  )

#-----------------------------------------------------------------------------
if(BUILD_TESTING)
  #  add_subdirectory(Testing)
endif()
