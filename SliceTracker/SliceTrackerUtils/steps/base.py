import logging
import qt, vtk
from abc import ABCMeta, abstractmethod

from ..session import SliceTrackerSession

from SlicerProstateUtils.decorators import logmethod
from SlicerProstateUtils.mixins import ModuleLogicMixin, ModuleWidgetMixin, GeneralModuleMixin


class StepBase(GeneralModuleMixin):

  MODULE_NAME = "SliceTracker"

  def getSetting(self, setting, moduleName=None, default=None):
    return GeneralModuleMixin.getSetting(self, setting, moduleName=self.MODULE_NAME, default=default)

  def setSetting(self, setting, value, moduleName=None):
    return GeneralModuleMixin.setSetting(self, setting, value, moduleName=self.MODULE_NAME)


class SliceTrackerStepLogic(StepBase, ModuleLogicMixin):

  __metaclass__ = ABCMeta

  def __init__(self):
    self.session = SliceTrackerSession()

  @abstractmethod
  def cleanup(self):
    pass


class SliceTrackerStep(qt.QWidget, StepBase, ModuleWidgetMixin):

  ActivatedEvent = vtk.vtkCommand.UserEvent + 150
  DeactivatedEvent = vtk.vtkCommand.UserEvent + 151

  NAME = None
  LogicClass = None

  @property
  def active(self):
    return self._activated

  @active.setter
  def active(self, value):
    if self.active == value:
      return
    self._activated = value
    logging.debug("%s %s" % ("activated" if self.active else "deactivate", self.NAME))
    self.invokeEvent(self.ActivatedEvent if self.active else self.DeactivatedEvent)
    if self.active:
      self.layoutManager.layoutChanged.connect(self.onLayoutChanged)
      self.setupSessionObservers()
    else:
      self.layoutManager.layoutChanged.disconnect(self.onLayoutChanged)
      self.removeSessionEventObservers()

  def __init__(self):
    qt.QWidget.__init__(self)
    self.session = SliceTrackerSession()
    if self.LogicClass:
      self.logic = self.LogicClass()
    self.setLayout(qt.QGridLayout())
    self.setup()
    self.setupConnections()
    self._activated = False

  def setupSessionObservers(self):
    self.session.addEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.addEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)
    self.session.addEventObserver(self.session.IncomingDataSkippedEvent, self.onIncomingDataSkipped)
    self.session.addEventObserver(self.session.NewImageDataReceivedEvent, self.onNewImageDataReceived)

  def removeSessionEventObservers(self):
    self.session.removeEventObserver(self.session.NewCaseStartedEvent, self.onNewCaseStarted)
    self.session.removeEventObserver(self.session.CloseCaseEvent, self.onCaseClosed)
    self.session.removeEventObserver(self.session.IncomingDataSkippedEvent, self.onIncomingDataSkipped)
    self.session.removeEventObserver(self.session.NewImageDataReceivedEvent, self.onNewImageDataReceived)

  @logmethod(logging.INFO)
  def onNewCaseStarted(self, caller, event):
    pass

  @logmethod(logging.INFO)
  def onCaseClosed(self, caller, event):
    pass

  @logmethod(logging.INFO)
  def onIncomingDataSkipped(self, caller, event):
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onNewImageDataReceived(self, caller, event, callData):
    pass

  def __del__(self):
    self.removeEventObservers()

  def cleanup(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setup(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def setupConnections(self):
    NotImplementedError("This method needs to be implemented for %s" % self.NAME)

  def onLayoutChanged(self):
    raise NotImplementedError("This method needs to be implemented for %s" % self.NAME)