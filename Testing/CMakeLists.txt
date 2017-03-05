macro(getExtensions subdirs directory)
  file(GLOB children RELATIVE ${directory} ${directory}/*)
  set(dirList "")
  foreach(child ${children})
    if(IS_DIRECTORY ${directory}/${child})
      list(APPEND dirList ${child})
    endif()
  endforeach()
  set(${subdirs} ${dirList})
endmacro()

if(NOT "$ENV{SLICER_EXTENSIONS_DIR}" STREQUAL "")
  getExtensions(possibleExtensions $ENV{SLICER_EXTENSIONS_DIR})

  set(ADDITIONAL_MODULE_PATHS "")

  foreach(subdir ${possibleExtensions})
    #message("${EXTENSION_DEPENDS}")
    string(FIND "${EXTENSION_DEPENDS}" "${subdir}" pos)
    if(${pos} GREATER -1)
      message("$ENV{SLICER_EXTENSIONS_DIR}/${subdir}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}")
      list(APPEND ADDITIONAL_MODULE_PATHS "$ENV{SLICER_EXTENSIONS_DIR}/${subdir}/${Slicer_QTSCRIPTEDMODULES_LIB_DIR}")
    endif()
    #ADD_SUBDIRECTORY(${subdir})
  endforeach()

  slicer_add_python_unittest(
    SCRIPT SliceTrackerTests.py
    SLICER_ARGS
      --additional-module-paths ${ADDITIONAL_MODULE_PATHS}
  )
else()
  slicer_add_python_unittest(SCRIPT SliceTrackerTests.py)
endif()