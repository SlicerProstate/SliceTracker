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
  NAME SliceTrackerZFrameRegistration
  SCRIPTS SliceTrackerZFrameRegistration.py
  RESOURCES ""
  )

slicerMacroBuildScriptedModule(
  NAME SurfaceCutToLabel
  SCRIPTS SurfaceCutToLabel.py
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )
