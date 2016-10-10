#-----------------------------------------------------------------------------
set(MODULE_NAME SliceTracker)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  SliceTrackerUtils/__init__.py
  SliceTrackerUtils/configuration.py
  SliceTrackerUtils/constants.py
  SliceTrackerUtils/exceptions.py
  SliceTrackerUtils/RegistrationData.py
  SliceTrackerUtils/ZFrameRegistration.py
  SliceTrackerUtils/helpers.py
  SliceTrackerUtils/watch.py
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
  Resources/Icons/icon-needle.png
  Resources/Icons/icon-revealCursor.png
  Resources/Icons/icon-skip.png
  Resources/Icons/icon-template.png
  Resources/Icons/icon-text-info.png
  Resources/Icons/icon-zframe.png
  Resources/Icons/SliceTracker.png
  Resources/Icons/${MODULE_NAME}.png
  Resources/zframe/zframe-model.vtk
  Resources/zframe/zframe-config.csv
  Resources/zframe/ProstateTemplate.csv
  Resources/default.cfg
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

slicerMacroBuildScriptedModule(
  NAME VolumeClipToLabel
  SCRIPTS VolumeClipToLabel.py
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  WITH_GENERIC_TESTS
  )
