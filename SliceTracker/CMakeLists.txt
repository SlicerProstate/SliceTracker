#-----------------------------------------------------------------------------
set(MODULE_NAME SliceTracker)

file(GLOB_RECURSE MODULE_PYTHON_SCRIPTS RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}
  *.py
)

file(GLOB_RECURSE MODULE_PYTHON_RESOURCES RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}
  ${PROJECT_SOURCE_DIR}/${MODULE_NAME}/Resources/*
)

#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )

slicerMacroBuildScriptedModule(
  NAME SliceTrackerRegistration
  SCRIPTS SliceTrackerRegistration.py
  RESOURCES ""
  )

slicerMacroBuildScriptedModule(
  NAME SurfaceCutToLabel
  SCRIPTS SurfaceCutToLabel.py
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )

# Get the current working branch
execute_process(
  COMMAND git rev-parse --abbrev-ref HEAD
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  OUTPUT_VARIABLE GIT_BRANCH
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

# Get the latest abbreviated commit hash of the working branch
execute_process(
  COMMAND git log -1 --format=%h
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  OUTPUT_VARIABLE GIT_COMMIT_HASH
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

execute_process(COMMAND ${GIT_EXECUTABLE} config --get remote.origin.url
  WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
  OUTPUT_VARIABLE GIT_WC_URL
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

configure_file(
  ${CMAKE_CURRENT_SOURCE_DIR}/Resources/version.json.in
  ${CMAKE_CURRENT_SOURCE_DIR}/Resources/version.json
)
