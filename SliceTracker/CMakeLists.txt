#-----------------------------------------------------------------------------
set(MODULE_NAME SliceTracker)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  SliceTrackerUtils/__init__.py
  SliceTrackerUtils/steps/__init__.py
  SliceTrackerUtils/steps/base.py
  SliceTrackerUtils/steps/plugins/__init__.py
  SliceTrackerUtils/steps/plugins/training.py
  SliceTrackerUtils/steps/plugins/results.py
  SliceTrackerUtils/steps/plugins/targets.py
  SliceTrackerUtils/steps/plugins/targeting.py
  SliceTrackerUtils/steps/plugins/needle.py
  SliceTrackerUtils/steps/plugins/segmentation/__init__.py
  SliceTrackerUtils/steps/plugins/segmentation/base.py
  SliceTrackerUtils/steps/plugins/segmentation/manual.py
  SliceTrackerUtils/steps/plugins/segmentation/automatic.py
  SliceTrackerUtils/steps/plugins/case.py
  SliceTrackerUtils/steps/overview.py
  SliceTrackerUtils/steps/segmentation.py
  SliceTrackerUtils/steps/zFrameRegistration.py
  SliceTrackerUtils/steps/evaluation.py
  SliceTrackerUtils/algorithms/__init__.py
  SliceTrackerUtils/algorithms/zFrameRegistration.py
  SliceTrackerUtils/configuration.py
  SliceTrackerUtils/constants.py
  SliceTrackerUtils/session.py
  SliceTrackerUtils/sessionData.py
  SliceTrackerUtils/helpers.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Colors/mpReviewColors.csv
  Resources/Icons/icon-cancelSegmentation.png
  Resources/Icons/icon-new.png
  Resources/Icons/icon-edit.png
  Resources/Icons/icon-open.png
  Resources/Icons/icon-close.png
  Resources/Icons/icon-back.png
  Resources/Icons/icon-start.png
  Resources/Icons/icon-retry.png
  Resources/Icons/icon-thumbsUp.png
  Resources/Icons/icon-thumbsDown.png
  Resources/Icons/icon-redo.png
  Resources/Icons/icon-undo.png
  Resources/Icons/icon-apply.png
  Resources/Icons/icon-newImageData.png
  Resources/Icons/icon-quickSegmentation.png
  Resources/Icons/icon-settings.png
  Resources/Icons/icon-infoBox.png
  Resources/Icons/icon-needle.png
  Resources/Icons/icon-revealCursor.png
  Resources/Icons/icon-skip.png
  Resources/Icons/icon-track.png
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
  NAME VolumeClipToLabel
  SCRIPTS VolumeClipToLabel.py
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )
