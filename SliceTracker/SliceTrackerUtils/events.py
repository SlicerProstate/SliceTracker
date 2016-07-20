import vtk

class SliceTrackerEvents(object):

  NewImageDataReceivedEvent = vtk.vtkCommand.UserEvent + 100
  NewFileIndexedEvent = vtk.vtkCommand.UserEvent + 101