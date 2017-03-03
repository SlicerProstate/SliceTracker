import slicer
import unittest

from SliceTrackerUtils.helpers import SliceTrackerSession

__all__ = ['SliceTrackerSessionTests']


class SliceTrackerSessionTests(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.session = SliceTrackerSession()
    cls.tempDir = slicer.app.temporaryPath

  def runTest(self):
    self.test_SliceTrackerSessionEvents()
    self.test_SliceTrackerSessionSingleton()

  def test_SliceTrackerSessionEvents(self):
    self.directoryChangedEventCalled = False
    self.session.addEventObserver(self.session.DirectoryChangedEvent,
                                  lambda event,caller:setattr(self, "directoryChangedEventCalled", True))

    self.assertFalse(self.directoryChangedEventCalled)
    self.session.directory = self.tempDir
    self.assertTrue(self.directoryChangedEventCalled)

  def test_SliceTrackerSessionSingleton(self):
    session = SliceTrackerSession()
    self.assertTrue(self.session is session)
    self.assertTrue(session.directory == self.session.directory)