import slicer
import unittest

from SliceTrackerUtils.helpers import SliceTrackerSession

__all__ = ['SliceTrackerTest']


class SliceTrackerTest(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.session = SliceTrackerSession()
    cls.tempDir = slicer.app.temporaryPath

  def runTest(self):
    self.test_SliceTrackerSessionEvents()

  def test_SliceTrackerSessionEvents(self):
    self.directoryChangedEventCalled = False
    self.session.addEventObserver(self.session.DirectoryChangedEvent,
                                  lambda event,caller:setattr(self, "directoryChangedEventCalled", True))

    self.assertFalse(self.directoryChangedEventCalled)
    self.session.directory = self.tempDir
    self.assertTrue(self.directoryChangedEventCalled)
