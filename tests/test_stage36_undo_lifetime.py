"""Regression test for the deleted-QUndoStack GUI teardown failure."""

from PySide6.QtWidgets import QWidget
from gui.diagram_editor import DiagramEditor


def test_undo_buttons_after_scene_stack_deletion(qtbot):
    parent = QWidget()
    editor = DiagramEditor(parent=parent)
    qtbot.addWidget(parent)
    stack = editor.scene.undo_stack
    # Explicit deletion mimics the teardown order seen in the traceback.
    import shiboken6
    shiboken6.delete(stack)
    editor.update_undo_buttons()  # Must not raise RuntimeError.


def test_undo_buttons_normal_state(qtbot):
    editor = DiagramEditor()
    qtbot.addWidget(editor)
    editor.update_undo_buttons()
    assert not editor.undo_button.isEnabled()
    editor.scene.add_bus(1, bus_type="Slack")
    assert editor.undo_button.isEnabled()
