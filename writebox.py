from PyQt6.QtWidgets import (QMainWindow, QApplication, QPlainTextEdit, QMenuBar, QMenu, QTabBar, QVBoxLayout, QWidget,
QHBoxLayout, QPushButton, QSpinBox, QDialog, QListWidget, QMessageBox, QFileDialog, QUndoView, QFontDialog, QColorDialog,
QDoubleSpinBox, QToolBar, QGroupBox, QLineEdit, QCheckBox, QComboBox, QLabel)
from PyQt6.QtGui import QAction, QKeySequence, QIcon, QMouseEvent, QTextCursor, QWheelEvent, QUndoStack, QUndoCommand, QPixmap, QPainter, QPalette, QTextDocument, QColor, QActionGroup, QCloseEvent
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QEvent, QSize
from PyQt6.QtPrintSupport import QPrintDialog, QPrinter, QPageSetupDialog, QPrintPreviewWidget
import sys
import os
import language_tool_python
import threading
import chardet
import argparse
from enum import Enum
import re
import webbrowser
import urllib.parse


def GetResourcePath(base: str, resourceName: str):
    if getattr(sys, 'frozen', False):  # If running as a PyInstaller bundle
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        base_path = os.path.dirname(__file__)  # Path to the script location
    return os.path.join(base_path, "res", base, resourceName)

def GetIconForResource(base: str, resourceName: str):
    pixmap = QPixmap(GetResourcePath(base, resourceName))
    color = app.palette().text().color()

    tinted_pixmap = QPixmap(pixmap.size())
    tinted_pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(tinted_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted_pixmap.rect(), color)
    painter.end()

    return QIcon(tinted_pixmap)

lang_tool = None
lang_tool_loader = None

class LanguageToolLoader(QObject):
    tool_ready = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.language_tool = None
        self.Thread = threading.Thread(target=self.initialize_tool)
        self.Thread.start()

    def initialize_tool(self):
        global lang_tool
        lang_tool = language_tool_python.LanguageTool("en-US")
        self.tool_ready.emit()  # Emit signal when the tool is ready

class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.ActionsInitialized = False
        self.setGeometry(200, 200, 800, 600)
        self.setWindowTitle("Untitled - WriteBox")
        self.setWindowIcon(QIcon(GetResourcePath("imgs", "logo.png")))

        # Create a central widget and set it as the central widget for the main window
        self.CentralWidget = QWidget(self)
        self.setCentralWidget(self.CentralWidget)

        global lang_tool_loader
        lang_tool_loader = LanguageToolLoader()

        # Create a layout for the central widget
        self.Layout = QVBoxLayout(self.CentralWidget)

        # Create a tab bar and text box
        self.TabBarLayout = QHBoxLayout(self.CentralWidget)
        self.TabBar = CustomTabBar(self)
        self.TabBar.setSelectionBehaviorOnRemove(QTabBar.SelectionBehavior.SelectPreviousTab)
        self.TabBar.setMovable(True)
        self.TabBar.addTab("Untitled")
        self.TabBar.setShape(QTabBar.Shape.RoundedSouth)
        self.TabBar.currentChanged.connect(self.TabSelected)

        self.NewTabButton = QPushButton(self)
        self.NewTabButton.setIcon(GetIconForResource("imgs", "add.svg"))
        self.NewTabButton.setFixedWidth(25)

        self.TextBox = CustomPlainTextEdit(self)
        self.TextBox.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.TextBox.textChanged.connect(self.TextChanged)
        self.TextBox.cursorPositionChanged.connect(self.TextCursorPositionChanged)
        self.TextBox.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.TextBox.customContextMenuRequested.connect(self.TextBoxContextMenuRequested)
        self.Font = self.TextBox.font()

        self.Printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)

        self.InitActions()
        self.AssignActionIcons()
        self.InitMenuBar()
        self.InitToolBar()

        self.ToggleCloseButtons()

        self.TabBar.tabInserted = self.TabAdded
        self.TabBar.tabRemoved = self.TabRemoved
        self.NewTabButton.clicked.connect(self.NewFileAction.trigger)

        # Add the tab bar and text box to the layout
        self.TabBarLayout.addWidget(self.TabBar)
        self.TabBarLayout.addWidget(self.NewTabButton)

        self.Layout.addLayout(self.TabBarLayout)
        self.Layout.addWidget(self.TextBox)
        self.Layout.setContentsMargins(2, 2, 2, 2)

        self.ToggleCloseButtons()

        self.LastNonFullscreenState = None
        self.OpenTabs = {
            0: TabInfo()
        }

        self.UndoTimer = QTimer(self)
        self.UndoTimer.setSingleShot(True)  # Trigger once
        self.UndoTimer.timeout.connect(self.PushUndo)  # Connect timeout to the function

        self.TextBox.copyAvailable.connect(self.CopyAvailable)
        
        self.history_window = None
        self.PPrevWidget = None

        self.ParseArgs()

    def ParseArgs(self):
        self.parser = argparse.ArgumentParser(
            prog="WriteBox",
            description="WriteBox is a simple text editing application.",
            formatter_class=argparse.HelpFormatter,
            prefix_chars="/"
        )
        self.parser.add_argument('filename', type=str, nargs='?', help='The file path to open.')
        self.parser.add_argument('/e', type=str, help='The encoding to open the file in, if a file path is specified.')

        args = self.parser.parse_args()
        
        if args.filename:
            if os.path.exists(args.filename):
                idx = self.TabBar.addTab(os.path.basename(args.filename))
                if args.e:
                    try:
                        self.OpenTabs[idx] = TabInfo(args.filename, args.e)
                    except Exception as ex:
                        self.parser.error(ex)

                    self.TabBar.setCurrentIndex(idx)
                else:
                    self.OpenTabs[idx] = TabInfo(args.filename)
                    self.TabBar.setCurrentIndex(idx)

                self.ToggleCloseButtons()
            else:
                self.parser.error("The file specified doesn't exist.")


    def closeEvent(self, event: QCloseEvent):
        for idx, tab in self.OpenTabs.items():
            res = tab.AskSave()
            match res:
                case AskSaveResult.SaveCurrent:
                    tab.Save()
                    event.accept()
                    break
                case AskSaveResult.SaveAll:
                    self.SaveAllTabs()
                    event.accept()
                    break
                case AskSaveResult.Cancel:
                    event.ignore()
                    return
        app.quit()
        super().closeEvent(event)

    

    def PrintPreview(self):
        if self.PrintPreviewAction.isChecked():
            self.PrintPrevConnections = []
            self.PPrevWidget = ZoomablePrintPreviewWidget(self.Printer, self)
            self.Layout.replaceWidget(self.TextBox, self.PPrevWidget, Qt.FindChildOption.FindDirectChildrenOnly)
            self.PPrevWidget.paintRequested.connect(self.PrintPreviewPaintRequested)
            self.PPrevWidget.updatePreview()
            self.MenuBar.hide()
            self.ToolBar.deleteLater()
            self.TabBar.hide()
            self.NewTabButton.hide()
            self.PrintPreviewToolbar = UnhidableToolbar("Print Preview Toolbar", self)
            self.addToolBar(self.PrintPreviewToolbar)
            self.PrintPreviewToolbar.addAction(self.PrintPrevExitAction)
            self.PrintPreviewToolbar.addAction(self.PrintAction)
            self.PrintPreviewToolbar.addAction(self.PageSetupAction)
            self.PrintPreviewToolbar.addSeparator()
            grp = QActionGroup(self)
            grp.addAction(self.PrintPrevFitWindowAction)
            grp.addAction(self.PrintPrevFitWidthAction)
            grp.addAction(self.PrintPrevCustomZoomAction)
            grp.setExclusive(True)
            self.PrintPreviewToolbar.addAction(self.PrintPrevFitWindowAction)
            self.PrintPreviewToolbar.addAction(self.PrintPrevFitWidthAction)
            self.PrintPreviewToolbar.addAction(self.PrintPrevCustomZoomAction)
            self.PrintPrevConnections.append((self.PrintPrevFitWindowAction.triggered, self.PrintPrevFitWindowAction.triggered.connect(lambda: self.SetPrintPrevZoomMode(QPrintPreviewWidget.ZoomMode.FitInView))))
            self.PrintPrevConnections.append((self.PrintPrevFitWidthAction.triggered, self.PrintPrevFitWidthAction.triggered.connect(lambda: self.SetPrintPrevZoomMode(QPrintPreviewWidget.ZoomMode.FitToWidth))))
            self.PrintPrevConnections.append((self.PrintPrevCustomZoomAction.triggered, self.PrintPrevCustomZoomAction.triggered.connect(lambda: self.SetPrintPrevZoomMode(QPrintPreviewWidget.ZoomMode.CustomZoom))))
            self.PPrevZoomBox = QDoubleSpinBox(self)
            self.PPrevZoomBox.setAccelerated(True)
            self.PPrevZoomBox.setRange(5, 600)
            self.PPrevZoomBox.setValue(100)
            self.PPrevZoomBox.setSuffix("%")
            self.PPrevWidget.previewChanged.connect(self.UpdatePrintPreview)
            self.PPrevZoomBox.valueChanged.connect(self.PrintPrevZoomChanged)
            self.PrintPreviewToolbar.addWidget(self.PPrevZoomBox)
            self.PrintPreviewToolbar.addAction(self.FullScreenAction)
            self.PrintPrevFitWindowAction.setChecked(True)
            self.PrintPreviewToolbar.addSeparator()
            self.PrintPreviewToolbar.addAction(self.PrintPrevPortraitAction)
            self.PrintPreviewToolbar.addAction(self.PrintPrevLandscapeAction)
            self.PrintPrevConnections.append((self.PrintPrevLandscapeAction.triggered, self.PrintPrevLandscapeAction.triggered.connect(self.PPrevWidget.setLandscapeOrientation)))
            self.PrintPrevConnections.append((self.PrintPrevLandscapeAction.triggered, self.PrintPrevPortraitAction.triggered.connect(self.PPrevWidget.setPortraitOrientation)))

            self.PrintPrevPageBox = QSpinBox(self)
            self.PrintPrevPageBox.setRange(1, self.PPrevWidget.pageCount())
            self.PrintPrevPageBox.setSuffix(" / " + str(self.PPrevWidget.pageCount()))
            self.PrintPrevPageBox.setValue(1)

            self.PrintPreviewToolbar.addSeparator()
            self.PrintPreviewToolbar.addAction(self.PrintPrevFirstPageAction)
            self.PrintPreviewToolbar.addAction(self.PrintPrevPrevPageAction)
            self.PrintPreviewToolbar.addWidget(self.PrintPrevPageBox)
            self.PrintPreviewToolbar.addAction(self.PrintPrevNextPageAction)
            self.PrintPreviewToolbar.addAction(self.PrintPrevLastPageAction)

            self.PrintPrevConnections.append((self.PrintPrevFirstPageAction.triggered, self.PrintPrevFirstPageAction.triggered.connect(self.PrintPrevFirstPage)))
            self.PrintPrevConnections.append((self.PrintPrevNextPageAction.triggered, self.PrintPrevNextPageAction.triggered.connect(self.PrintPrevNextPage)))
            self.PrintPrevConnections.append((self.PrintPrevLastPageAction.triggered, self.PrintPrevLastPageAction.triggered.connect(self.PrintPrevLastPage)))
            self.PrintPrevConnections.append((self.PrintPrevPrevPageAction.triggered, self.PrintPrevPrevPageAction.triggered.connect(self.PrintPrevPrevPage)))

            self.PrintPrevPageBox.valueChanged.connect(lambda val: self.PPrevWidget.setCurrentPage(val))

            self.PrintPreviewToolbar.addSeparator()

            self.PrintPreviewToolbar.addAction(self.PrintPrevViewSingleAction)
            self.PrintPreviewToolbar.addAction(self.PrintPrevViewFacingAction)
            self.PrintPreviewToolbar.addAction(self.PrintPrevViewAllAction)

            self.PrintPrevViewSingleAction.setChecked(True)

            self.PrintPrevConnections.append((self.PrintPrevViewSingleAction.triggered, self.PrintPrevViewSingleAction.triggered.connect(self.PPrevWidget.setSinglePageViewMode)))
            self.PrintPrevConnections.append((self.PrintPrevViewFacingAction.triggered, self.PrintPrevViewFacingAction.triggered.connect(self.PPrevWidget.setFacingPagesViewMode)))
            self.PrintPrevConnections.append((self.PrintPrevViewAllAction.triggered, self.PrintPrevViewAllAction.triggered.connect(self.PPrevWidget.setAllPagesViewMode)))

            self.UpdatePrintPreview()

        else:
            self.Layout.replaceWidget(self.PPrevWidget, self.TextBox, Qt.FindChildOption.FindDirectChildrenOnly)
            self.PPrevWidget.deleteLater()
            self.MenuBar.show()
            self.InitToolBar()
            self.TabBar.show()
            self.NewTabButton.show()
            if self.PrintPreviewToolbar:
                self.PrintPreviewToolbar.deleteLater()

            for signal, slot in self.PrintPrevConnections:
                signal.disconnect(slot)

    def PrintPrevFirstPage(self):
        self.PPrevWidget.setCurrentPage(1)
        self.UpdatePrintPreview()

    def PrintPrevNextPage(self):
        self.PPrevWidget.setCurrentPage(self.PPrevWidget.currentPage() + 1)
        self.UpdatePrintPreview()

    def PrintPrevLastPage(self):
        self.PPrevWidget.setCurrentPage(self.PPrevWidget.pageCount())
        self.UpdatePrintPreview()

    def PrintPrevPrevPage(self):
        self.PPrevWidget.setCurrentPage(self.PPrevWidget.currentPage() - 1)
        self.UpdatePrintPreview()

    def PrintPrevZoomChanged(self):
        self.PPrevWidget.setZoomFactor(self.PPrevZoomBox.value() / 100)
        if self.PPrevWidget.zoomMode() == QPrintPreviewWidget.ZoomMode.CustomZoom:
            self.PrintPrevCustomZoomAction.setChecked(True)

    def UpdatePrintPreview(self):
        self.PPrevZoomBox.blockSignals(True)
        self.PPrevZoomBox.setValue(self.PPrevWidget.zoomFactor() * 100)
        self.PPrevZoomBox.blockSignals(False)
        
        # if self.PPrevWidget.orientation() == Qt.Orientation.Horizontal:
        #     self.PrintPrevPortraitAction.blockSignals(True)
        #     self.PrintPrevLandscapeAction.blockSignals(True)
        #     self.PrintPrevLandscapeAction.setChecked(True)
        #     self.PrintPrevPortraitAction.setChecked(False)
        #     self.PrintPrevLandscapeAction.blockSignals(False)
        #     self.PrintPrevPortraitAction.blockSignals(False)
        # else:
        #     self.PrintPrevPortraitAction.blockSignals(True)
        #     self.PrintPrevLandscapeAction.blockSignals(True)
        #     self.PrintPrevPortraitAction.setChecked(True)
        #     self.PrintPrevLandscapeAction.setChecked(False)
        #     self.PrintPrevPortraitAction.blockSignals(False)
        #     self.PrintPrevLandscapeAction.blockSignals(False)
        
        self.PrintPrevFirstPageAction.setEnabled(self.PPrevWidget.currentPage() != 1)
        self.PrintPrevPrevPageAction.setEnabled(self.PPrevWidget.currentPage() != 1)
        self.PrintPrevLastPageAction.setEnabled(self.PPrevWidget.currentPage() != self.PPrevWidget.pageCount())
        self.PrintPrevNextPageAction.setEnabled(self.PPrevWidget.currentPage() != self.PPrevWidget.pageCount())
        
        self.PrintPrevPageBox.blockSignals(True)
        self.PrintPrevPageBox.setValue(self.PPrevWidget.currentPage())
        self.PrintPrevPageBox.blockSignals(False)

    def SetPrintPrevZoomMode(self, zoomMode: QPrintPreviewWidget.ZoomMode):
        self.PPrevWidget.setZoomMode(zoomMode)

    def PrintPreviewPaintRequested(self, printer: QPrinter):
        doc = QTextDocument(self.TextBox.toPlainText())
        doc.setDefaultFont(self.TextBox.font())
        fnt = f"font-family:{self.TextBox.font().family()}; font-size:{self.TextBox.font().pointSizeF()}pt;"
        tc = self.palette().text().color()
        tcol = QColor(255 - tc.red(), 255 - tc.green(), 255 - tc.blue(), tc.alpha())

        content = f'<span style="{fnt} color: rgba({tcol.red()},{tcol.green()},{tcol.blue()},{tcol.alphaF()});"> {self.TextBox.toPlainText()} </span>'

        doc.setHtml(content)
        doc.print(printer)

    def InitActions(self):
        # File actions
        self.NewFileAction = QAction(self)
        self.NewFileAction.setText("New")
        self.NewFileAction.setShortcut(QKeySequence.StandardKey.New)
        self.NewFileAction.triggered.connect(self.AddTab)

        self.OpenFileAction = QAction(self)
        self.OpenFileAction.setText("Open")
        self.OpenFileAction.setShortcut(QKeySequence.StandardKey.Open)
        self.OpenFileAction.triggered.connect(self.Open)

        self.SaveFileAction = QAction(self)
        self.SaveFileAction.setText("Save")
        self.SaveFileAction.setShortcut(QKeySequence.StandardKey.Save)
        self.SaveFileAction.triggered.connect(lambda: self.OpenTabs[self.TabBar.currentIndex()].Save())

        self.SaveFileAsAction = QAction(self)
        self.SaveFileAsAction.setText("Save As")
        self.SaveFileAsAction.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.SaveFileAsAction.triggered.connect(lambda: self.OpenTabs[self.TabBar.currentIndex()].SaveAs())

        self.SaveAllFilesAction = QAction(self)
        self.SaveAllFilesAction.setText("Save All")
        self.SaveAllFilesAction.triggered.connect(self.SaveAllTabs)

        self.PrintAction = QAction(self)
        self.PrintAction.setText("Print")
        self.PrintAction.setShortcut(QKeySequence.StandardKey.Print)
        self.PrintAction.triggered.connect(self.Print)

        self.PageSetupAction = QAction(self)
        self.PageSetupAction.setText("Page Setup")
        self.PageSetupAction.triggered.connect(self.PageSetup)
        
        self.PrintPreviewAction = QAction(self)
        self.PrintPreviewAction.setText("Print Preview")
        self.PrintPreviewAction.setCheckable(True)
        self.PrintPreviewAction.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self.PrintPreviewAction.triggered.connect(self.PrintPreview)

        self.SettingsAction = QAction(self)
        self.SettingsAction.setText("Settings")
        self.SettingsAction.setShortcut(QKeySequence.StandardKey.Preferences)

        self.AboutAction = QAction(self)
        self.AboutAction.setText("About WriteBox...")
        self.AboutAction.triggered.connect(self.About)
        self.AboutAction.setShortcut(QKeySequence.StandardKey.HelpContents)

        self.CloseAction = QAction(self)
        self.CloseAction.setText("Close Tab")
        self.CloseAction.setShortcuts([QKeySequence("Ctrl+W"), QKeySequence.StandardKey.Close])
        self.CloseAction.triggered.connect(lambda: self.CloseTab(self.TabBar.currentIndex()))

        self.ExitAction = QAction(self)
        self.ExitAction.setText("Exit")
        self.ExitAction.setShortcut(QKeySequence.StandardKey.Quit)
        self.ExitAction.triggered.connect(self.close)

        # Edit actions
        self.UndoAction = QAction(self)
        self.UndoAction.setText("Undo")
        self.UndoAction.setShortcut(QKeySequence.StandardKey.Undo)
        self.UndoAction.triggered.connect(self.Undo)
        self.UndoAction.setEnabled(False)

        self.RedoAction = QAction(self)
        self.RedoAction.setText("Redo")
        self.RedoAction.setShortcut(QKeySequence.StandardKey.Redo)
        self.RedoAction.triggered.connect(self.Redo)
        self.RedoAction.setEnabled(False)

        self.HistoryAction = QAction(self)
        self.HistoryAction.setText("History")
        self.HistoryAction.setShortcut(QKeySequence("Alt+H"))
        self.HistoryAction.setCheckable(True)
        self.HistoryAction.triggered.connect(self.ToggleHistoryWindow)

        self.CutAction = QAction(self)
        self.CutAction.setText("Cut")
        self.CutAction.setShortcut(QKeySequence.StandardKey.Cut)
        self.CutAction.setEnabled(False)
        self.CutAction.triggered.connect(self.TextBox.cut)

        self.CopyAction = QAction(self)
        self.CopyAction.setText("Copy")
        self.CopyAction.setShortcut(QKeySequence.StandardKey.Copy)
        self.CopyAction.setEnabled(False)
        self.CopyAction.triggered.connect(self.TextBox.copy)

        self.PasteAction = QAction(self)
        self.PasteAction.setText("Paste")
        self.PasteAction.setShortcut(QKeySequence.StandardKey.Paste)
        self.PasteAction.setEnabled(self.TextBox.canPaste())
        self.PasteAction.triggered.connect(self.TextBox.paste)

        self.SpellGrammarCheckAction = QAction(self)
        self.SpellGrammarCheckAction.setText("Spell/Grammar Check")
        self.SpellGrammarCheckAction.setShortcut(QKeySequence("F7"))
        self.SpellGrammarCheckAction.triggered.connect(lambda: SpellCheckDialog(self.TextBox, self).exec())

        self.FindReplaceAction = QAction(self)
        self.FindReplaceAction.setText("Find/Replace")
        self.FindReplaceAction.setShortcuts([QKeySequence.StandardKey.Replace, QKeySequence.StandardKey.Find])
        self.FindReplaceAction.triggered.connect(lambda: FindReplaceDialog(self, self.TextBox, self.TextBox.textCursor()).exec())

        # View actions
        self.ZoomInAction = QAction(self)
        self.ZoomInAction.setText("Zoom In")
        self.ZoomInAction.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.ZoomInAction.triggered.connect(self.TextBox.ZoomIn)

        self.ZoomOutAction = QAction(self)
        self.ZoomOutAction.setText("Zoom Out")
        self.ZoomOutAction.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.ZoomOutAction.triggered.connect(self.TextBox.ZoomOut)

        self.ZoomResetAction = QAction(self)
        self.ZoomResetAction.setText("Reset Zoom")
        self.ZoomResetAction.setShortcut(QKeySequence("Ctrl+0"))
        self.ZoomResetAction.triggered.connect(lambda: self.TextBox.SetZoomLevel(1))

        self.FullScreenAction = QAction(self)
        self.FullScreenAction.setText("Full-Screen Mode")
        self.FullScreenAction.setShortcut(QKeySequence.StandardKey.FullScreen)
        self.FullScreenAction.setCheckable(True)
        self.FullScreenAction.triggered.connect(self.ToggleFullscreen)

        self.WordWrapAction = QAction(self)
        self.WordWrapAction.setText("Word wrapping")
        self.WordWrapAction.setCheckable(True)
        self.WordWrapAction.triggered.connect(lambda: self.TextBox.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth if self.WordWrapAction.isChecked() else QPlainTextEdit.LineWrapMode.NoWrap))

        self.EditFontAction = QAction(self)
        self.EditFontAction.setText("Edit Font...")
        self.EditFontAction.triggered.connect(self.EditFont)

        self.EditFontColorAction = QAction(self)
        self.EditFontColorAction.setText("Edit Font Color...")
        self.EditFontColorAction.triggered.connect(self.EditFontColor)

        # Help actions
        self.AboutQtAction = QAction(self)
        self.AboutQtAction.setText("About Qt...")
        self.AboutQtAction.triggered.connect(app.aboutQt)

        # Other actions
        self.PrintPrevExitAction = QAction(self)
        self.PrintPrevExitAction.setText("Exit Print Preview (Ctrl + Shift + P)")
        self.PrintPrevExitAction.triggered.connect(self.PrintPreviewAction.trigger)

        self.PrintPrevFitWindowAction = QAction(self)
        self.PrintPrevFitWindowAction.setText("Fit to Window")
        self.PrintPrevFitWindowAction.setCheckable(True)

        self.PrintPrevFitWidthAction = QAction(self)
        self.PrintPrevFitWidthAction.setText("Fit to Width")
        self.PrintPrevFitWidthAction.setCheckable(True)

        self.PrintPrevCustomZoomAction = QAction(self)
        self.PrintPrevCustomZoomAction.setText("Custom")
        self.PrintPrevCustomZoomAction.setCheckable(True)

        self.PrintPrevOrientationGroup = QActionGroup(self)
        self.PrintPrevOrientationGroup.setExclusive(True)

        self.PrintPrevLandscapeAction = QAction(self)
        self.PrintPrevLandscapeAction.setText("Landscape")
        self.PrintPrevOrientationGroup.addAction(self.PrintPrevLandscapeAction)
        self.PrintPrevLandscapeAction.setCheckable(True)

        self.PrintPrevPortraitAction = QAction(self)
        self.PrintPrevPortraitAction.setText("Portrait")
        self.PrintPrevOrientationGroup.addAction(self.PrintPrevPortraitAction)
        self.PrintPrevPortraitAction.setCheckable(True)

        self.PrintPrevPrevPageAction = QAction(self)
        self.PrintPrevPrevPageAction.setText("Previous page")

        self.PrintPrevLastPageAction = QAction(self)
        self.PrintPrevLastPageAction.setText("Jump to Last Page")

        self.PrintPrevNextPageAction = QAction(self)
        self.PrintPrevNextPageAction.setText("Next page")

        self.PrintPrevFirstPageAction = QAction(self)
        self.PrintPrevFirstPageAction.setText("Jump to First Page")

        self.PrintPrevViewGroup = QActionGroup(self)
        self.PrintPrevViewGroup.setExclusive(True)

        self.PrintPrevViewSingleAction = QAction(self)
        self.PrintPrevViewSingleAction.setText("Single-page View")
        self.PrintPrevViewSingleAction.setCheckable(True)
        self.PrintPrevViewGroup.addAction(self.PrintPrevViewSingleAction)

        self.PrintPrevViewFacingAction = QAction(self)
        self.PrintPrevViewFacingAction.setText("Facing Pages View")
        self.PrintPrevViewFacingAction.setCheckable(True)
        self.PrintPrevViewGroup.addAction(self.PrintPrevViewFacingAction)

        self.PrintPrevViewAllAction = QAction(self)
        self.PrintPrevViewAllAction.setText("Full View")
        self.PrintPrevViewAllAction.setCheckable(True)
        self.PrintPrevViewGroup.addAction(self.PrintPrevViewAllAction)

        self.ActionsInitialized = True

    def InitMenuBar(self):
        self.MenuBar = QMenuBar(self)

        # File Menu
        self.FileMenu = QMenu("File", self)
        self.FileMenu.addAction(self.NewFileAction)
        self.FileMenu.addAction(self.OpenFileAction)
        self.FileMenu.addAction(self.SaveFileAction)
        self.FileMenu.addAction(self.SaveFileAsAction)
        self.FileMenu.addAction(self.SaveAllFilesAction)
        self.FileMenu.addSeparator()
        self.FileMenu.addAction(self.PrintAction)
        self.FileMenu.addAction(self.PageSetupAction)
        self.FileMenu.addAction(self.PrintPreviewAction)
        self.FileMenu.addSeparator()
        #self.FileMenu.addAction(self.SettingsAction)
        self.FileMenu.addAction(self.AboutAction)
        self.FileMenu.addAction(self.CloseAction)
        self.FileMenu.addAction(self.ExitAction)

        # Edit Menu
        self.EditMenu = QMenu("Edit", self)
        self.EditMenu.addAction(self.UndoAction)
        self.EditMenu.addAction(self.RedoAction)
        self.EditMenu.addAction(self.HistoryAction)
        self.EditMenu.addSeparator()
        self.EditMenu.addAction(self.CutAction)
        self.EditMenu.addAction(self.CopyAction)
        self.EditMenu.addAction(self.PasteAction)
        self.EditMenu.addAction(self.SpellGrammarCheckAction)
        self.EditMenu.addAction(self.FindReplaceAction)

        # View Menu
        self.ViewMenu = QMenu("View", self)
        self.ViewMenu.addAction(self.ZoomInAction)
        self.ViewMenu.addAction(self.ZoomOutAction)
        self.ViewMenu.addAction(self.ZoomResetAction)
        self.ViewMenu.addSeparator()
        self.ViewMenu.addAction(self.FullScreenAction)
        self.ViewMenu.addAction(self.WordWrapAction)
        self.ViewMenu.addAction(self.EditFontAction)
        self.ViewMenu.addAction(self.EditFontColorAction)

        # Help Menu
        self.HelpMenu = QMenu("Help", self)
        self.HelpMenu.addAction(self.AboutAction)
        self.HelpMenu.addAction(self.AboutQtAction)

        # Add menus to the menu bar
        self.MenuBar.addMenu(self.FileMenu)
        self.MenuBar.addMenu(self.EditMenu)
        self.MenuBar.addMenu(self.ViewMenu)
        self.MenuBar.addMenu(self.HelpMenu)

        self.setMenuBar(self.MenuBar)

    def InitToolBar(self):
        self.ToolBar = self.addToolBar("Toolbar")
        self.ToolBar.addAction(self.OpenFileAction)
        self.ToolBar.addAction(self.SaveFileAction)
        self.ToolBar.addAction(self.PrintAction)
        self.ToolBar.addSeparator()
        self.ToolBar.addAction(self.SpellGrammarCheckAction)
        self.ToolBar.addAction(self.FindReplaceAction)
        self.ToolBar.addSeparator()
        self.ToolBar.addAction(self.ZoomInAction)
        self.ToolBar.addAction(self.ZoomOutAction)
        self.ToolBar.addAction(self.ZoomResetAction)
        self.ZoomBox = QSpinBox(self)
        self.ZoomBox.setRange(8, 400)
        self.ZoomBox.setAccelerated(True)
        self.ZoomBox.setValue(100)
        self.ZoomBox.setToolTip("Zoom percentage")
        self.ZoomBox.setSuffix("%")
        self.TextBox.zoomLevelChanged.connect(lambda zoomLevel: self.ZoomBox.setValue(round(zoomLevel * 100)))
        self.ZoomBox.valueChanged.connect(lambda: self.TextBox.SetZoomLevel(self.ZoomBox.value() / 100))
        self.ToolBar.addWidget(self.ZoomBox)
        self.ToolBar.addAction(self.FullScreenAction)
        self.ToolBar.addSeparator()
        self.ToolBar.addAction(self.WordWrapAction)
        self.ToolBar.addSeparator()
        self.ToolBar.addAction(self.UndoAction)
        self.ToolBar.addAction(self.RedoAction)
        self.ToolBar.addAction(self.HistoryAction)
        self.ToolBar.addSeparator()
        self.ToolBar.addAction(self.CutAction)
        self.ToolBar.addAction(self.CopyAction)
        self.ToolBar.addAction(self.PasteAction)
        self.ToolBar.addSeparator()
        self.ToolBar.addAction(self.EditFontAction)

    def AssignActionIcons(self):
        self.NewFileAction.setIcon(GetIconForResource("imgs", "new.svg"))
        self.OpenFileAction.setIcon(GetIconForResource("imgs", "open.svg"))
        self.SaveFileAction.setIcon(GetIconForResource("imgs", "save.svg"))
        self.SaveFileAsAction.setIcon(GetIconForResource("imgs", "saveas.svg"))
        self.SaveAllFilesAction.setIcon(GetIconForResource("imgs", "save.svg"))
        self.PrintAction.setIcon(GetIconForResource("imgs", "print.svg"))
        self.PageSetupAction.setIcon(GetIconForResource("imgs", "pagesp.svg"))
        self.PrintPreviewAction.setIcon(GetIconForResource("imgs", "printprev.svg"))
        self.SettingsAction.setIcon(GetIconForResource("imgs", "config.svg"))
        self.AboutAction.setIcon(GetIconForResource("imgs", "info.svg"))
        self.CloseAction.setIcon(GetIconForResource("imgs", "close.svg"))
        self.ExitAction.setIcon(GetIconForResource("imgs", "exit.svg"))
        self.UndoAction.setIcon(GetIconForResource("imgs", "undo.svg"))
        self.RedoAction.setIcon(GetIconForResource("imgs", "redo.svg"))
        self.HistoryAction.setIcon(GetIconForResource("imgs", "history.svg"))
        self.CutAction.setIcon(GetIconForResource("imgs", "cut.svg"))
        self.CopyAction.setIcon(GetIconForResource("imgs", "copy.svg"))
        self.PasteAction.setIcon(GetIconForResource("imgs", "paste.svg"))
        self.SpellGrammarCheckAction.setIcon(GetIconForResource("imgs", "spgrcheck.svg"))
        self.FindReplaceAction.setIcon(GetIconForResource("imgs", "findreplace.svg"))
        self.ZoomInAction.setIcon(GetIconForResource("imgs", "zoomin.svg"))
        self.ZoomOutAction.setIcon(GetIconForResource("imgs", "zoomout.svg"))
        self.ZoomResetAction.setIcon(GetIconForResource("imgs", "zoomres.svg"))
        self.FullScreenAction.setIcon(GetIconForResource("imgs", "fullscreen.svg"))
        self.WordWrapAction.setIcon(GetIconForResource("imgs", "wwrap.svg"))
        self.EditFontAction.setIcon(GetIconForResource("imgs", "font.svg"))
        self.EditFontColorAction.setIcon(GetIconForResource("imgs", "paint.svg"))
        self.PrintPrevExitAction.setIcon(GetIconForResource("imgs", "exit.svg"))
        self.PrintPrevFitWindowAction.setIcon(GetIconForResource("imgs", "fitwin.svg"))
        self.PrintPrevFitWidthAction.setIcon(GetIconForResource("imgs", "fitwidth.svg"))
        self.PrintPrevCustomZoomAction.setIcon(GetIconForResource("imgs", "findreplace.svg"))
        self.PrintPrevLandscapeAction.setIcon(GetIconForResource("imgs", "orientlandscape.svg"))
        self.PrintPrevPortraitAction.setIcon(GetIconForResource("imgs", "orientportrait.svg"))
        self.PrintPrevPrevPageAction.setIcon(GetIconForResource("imgs", "back.svg"))
        self.PrintPrevFirstPageAction.setIcon(GetIconForResource("imgs", "backx.svg"))
        self.PrintPrevNextPageAction.setIcon(GetIconForResource("imgs", "fwd.svg"))
        self.PrintPrevLastPageAction.setIcon(GetIconForResource("imgs", "fwdx.svg"))
        self.PrintPrevViewSingleAction.setIcon(GetIconForResource("imgs", "printprevm0.svg"))
        self.PrintPrevViewFacingAction.setIcon(GetIconForResource("imgs", "printprevm1.svg"))
        self.PrintPrevViewAllAction.setIcon(GetIconForResource("imgs", "printprevm2.svg"))
        self.AboutQtAction.setIcon(GetIconForResource("imgs", "info.svg"))

    def ToggleFullscreen(self):
        if self.isFullScreen():
            self.setWindowState(self.LastNonFullscreenState)
            self.FullScreenAction.setIcon(QIcon(GetResourcePath("imgs", "fullscreen.svg")))
        else:
            self.LastNonFullscreenState = self.windowState()
            self.setWindowState(Qt.WindowState.WindowFullScreen)
            self.FullScreenAction.setIcon(QIcon(GetResourcePath("imgs", "fullscreenx.svg")))

    def TabAdded(self, index):
        self.ToggleCloseButtons()

    def TabRemoved(self, index):
        self.ToggleCloseButtons()

    def CloseTab(self, index):
        if self.TabBar.count() > 1:
            res = self.OpenTabs[index].AskSave()
            match res:
                case AskSaveResult.SaveAll:
                    self.SaveAllTabs()
                case AskSaveResult.SaveCurrent:
                    self.OpenTabs[index].Save()
                case AskSaveResult.Cancel:
                    return

            # Remove the tab from TabBar first
            self.TabBar.removeTab(index)
            
            del self.OpenTabs[index]
            updated_tabs = {}
            for key, value in self.OpenTabs.items():
                if key > index:
                    updated_tabs[key - 1] = value  # Shift down
                else:
                    updated_tabs[key] = value
            

            self.OpenTabs = updated_tabs
            self.TabSelected(self.TabBar.currentIndex())

            self.ToggleCloseButtons()

    def SaveAllTabs(self):
        for idx, tab in self.OpenTabs.items():
            if tab.FilePath:
                tab.Save()

    def PageSetup(self):
        dialog = QPageSetupDialog(self.Printer, self)
        dialog.exec()
        if self.PPrevWidget:
            self.PPrevWidget.updatePreview()
            self.UpdatePrintPreview()

    def Print(self):

        # Open the print dialog
        dialog = QPrintDialog(self.Printer, self)
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            # Print the contents of the QPlainTextEdit
            zoom = self.TextBox.zoomLevel
            self.TextBox.SetZoomLevel(1)
            self.TextBox.print(self.Printer)
            self.TextBox.SetZoomLevel(zoom)

    def changeEvent(self, event: QEvent):
        super().changeEvent(event)
        if self.ActionsInitialized:
            self.AssignActionIcons()
            self.ToggleCloseButtons()
            self.NewTabButton.setIcon(GetIconForResource("imgs", "add.svg"))

    def ToggleHistoryWindow(self):
        if self.HistoryAction.isChecked():
            self.history_window = QDialog(self, Qt.WindowType.Tool | Qt.WindowType.WindowCloseButtonHint)
            self.history_window.setFixedSize(250, 400)
            self.history_window.setWindowTitle("History")
            layout = QVBoxLayout(self.history_window)
            self.history_window.setLayout(layout)
            self.history_viewer = QUndoView(self.OpenTabs[self.TabBar.currentIndex()].UndoStack, self)
            layout.addWidget(self.history_viewer)
            self.history_window.show()
            self.history_window.closeEvent = lambda win: self.HistoryAction.setChecked(False)
        else:
            if self.history_window:
                self.history_window.close()

    def ToggleCloseButtons(self):
        if self.TabBar.count() > 1:
            self.CloseAction.setEnabled(True)
            for idx in range(self.TabBar.count()):
                btn = QPushButton(self)
                btn.setIcon(GetIconForResource("imgs", "close.svg"))
                btn.setIconSize(QSize(16, 16))
                btn.setFixedSize(QSize(16, 16))
                btn.clicked.connect(lambda b, i=idx: self.CloseTab(i))
                self.TabBar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, btn)
        else:
            self.CloseAction.setEnabled(False)
            for idx in range(self.TabBar.count()):
                self.TabBar.setTabButton(idx, QTabBar.ButtonPosition.RightSide, None)

    def TextBoxContextMenuRequested(self, pos):
        menu = QMenu(self)
        menu.addAction(self.UndoAction)
        menu.addAction(self.RedoAction)
        menu.addSeparator()
        menu.addAction(self.CutAction)
        menu.addAction(self.CopyAction)
        menu.addAction(self.PasteAction)
        menu.addSeparator()
        menu.addAction(self.ZoomInAction)
        menu.addAction(self.ZoomOutAction)
        menu.exec(self.mapToGlobal(pos))

    def PushUndo(self):
        command = EditCommand(self.TextBox, self.OpenTabs[self.TabBar.currentIndex()].Content, self.TextBox.toPlainText())
        self.OpenTabs[self.TabBar.currentIndex()].UndoStack.push(command)
        self.OpenTabs[self.TabBar.currentIndex()].Content = self.TextBox.toPlainText()

    def AddTab(self):
        index = self.TabBar.addTab("Untitled")
        self.OpenTabs[index] = TabInfo()
        self.ToggleCloseButtons()

    def Undo(self):
        self.OpenTabs[self.TabBar.currentIndex()].UndoStack.undo()
        self.UndoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canUndo())
        self.RedoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canRedo())
        self.OpenTabs[self.TabBar.currentIndex()].Content = self.TextBox.toPlainText()

    def Redo(self):
        self.OpenTabs[self.TabBar.currentIndex()].UndoStack.redo()
        self.UndoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canUndo())
        self.RedoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canRedo())
        self.OpenTabs[self.TabBar.currentIndex()].Content = self.TextBox.toPlainText()

    def TabSelected(self, index: int):
        self.TextBox.blockSignals(True)
        self.TextBox.setPlainText(self.OpenTabs[index].Content)
        cursor = self.TextBox.textCursor()
        cursor.setPosition(self.OpenTabs[index].CursorPos, QTextCursor.MoveMode.MoveAnchor)
        self.TextBox.setTextCursor(cursor)  # Explicitly set the cursor back
        self.TextBox.blockSignals(False)
        self.setWindowTitle(self.OpenTabs[index].GetTitle() + " - WriteBox")
        self.UndoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canUndo())
        self.RedoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canRedo())
        if self.history_window:
            self.history_viewer.setStack(self.OpenTabs[index].UndoStack)

    
    def About(self):
        QMessageBox.about(
            self,
            "About WriteBox",
            """
            WriteBox v1.0.0
            WriteBox is a simple plain-text editor.
            
            WriteBox uses Material Symbols, designed by Google.
            WriteBox is built with Qt for Python 6.
            """
        )

    def CopyAvailable(self, canCopy):
        self.CopyAction.setEnabled(canCopy)
        self.CutAction.setEnabled(canCopy)
        self.PasteAction.setEnabled(self.TextBox.canPaste())

    def EditFont(self):
        dlg = QFontDialog(self)
        dlg.setCurrentFont(self.Font)
        result = dlg.exec()

        if result == QFontDialog.DialogCode.Accepted:
            self.Font = dlg.currentFont()
            self.TextBox.setFont(self.Font)
            self.TextBox.defaultFontSize = self.Font.pointSizeF()
            self.TextBox.SetZoomLevel(self.TextBox.zoomLevel)

    def EditFontColor(self):
        dlg = QColorDialog(self)
        dlg.setOptions(QColorDialog.ColorDialogOption.ShowAlphaChannel)
        old_text_color = self.TextBox.palette().text().color()
        dlg.setCurrentColor(old_text_color)
        result = dlg.exec()

        if result == QFontDialog.DialogCode.Accepted:
            new_palette = self.TextBox.palette()
            new_palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, dlg.currentColor())
            self.TextBox.setPalette(new_palette)

    def TextChanged(self):

        if self.UndoTimer.isActive():
            self.UndoTimer.stop()

        # Start the timer
        self.UndoTimer.start(500)

        if not self.OpenTabs[self.TabBar.currentIndex()].IsLoading:
            self.OpenTabs[self.TabBar.currentIndex()].Modified = True

        self.OpenTabs[self.TabBar.currentIndex()].CursorPos = self.TextBox.textCursor().position()
        self.TabBar.setTabText(self.TabBar.currentIndex(), self.OpenTabs[self.TabBar.currentIndex()].GetTitle())
        self.setWindowTitle(self.OpenTabs[self.TabBar.currentIndex()].GetTitle() + " - WriteBox")
        self.UndoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canUndo())
        self.RedoAction.setEnabled(self.OpenTabs[self.TabBar.currentIndex()].UndoStack.canRedo())
        self.PasteAction.setEnabled(self.TextBox.canPaste())

    def TextCursorPositionChanged(self):
        self.OpenTabs[self.TabBar.currentIndex()].CursorPos = self.TextBox.textCursor().position()

    def Open(self):
        dlg = QFileDialog(self, "Open File", None, "Text files (*.txt);;All files (*.*)")
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dlg.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dlg.exec()
        for file in dlg.selectedFiles():
            idx = self.TabBar.addTab(os.path.basename(file))
            self.OpenTabs[idx] = TabInfo(file)
            self.TabBar.setCurrentIndex(idx)

        self.ToggleCloseButtons()

class CustomTabBar(QTabBar):
    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.RightButton:
            tabIndex = self.tabAt(event.pos())
            if tabIndex != -1:
                self.tabContextMenu(tabIndex).exec(event.globalPosition().toPoint())
        elif event.button() == Qt.MouseButton.MiddleButton:
            tabIndex = self.tabAt(event.pos())
            if tabIndex != -1 and self.count() > 1:
                self.removeTab(tabIndex)

    def tabContextMenu(self, index: int):
        menu = QMenu(self)
        menu.addAction("Close Tab", lambda: self.CloseTab(index)).setEnabled(self.count() > 1)
        menu.addAction("Close Other Tabs", lambda: self.CloseOtherTabs(index)).setEnabled(self.count() > 1)
        return menu

    def CloseTab(self, index: int):
        if index >= 0 and self.count() > 1:
            self.removeTab(index)

    def CloseOtherTabs(self, index: int):
        for i in range(self.count() - 1, -1, -1):
            if i != index:
                self.removeTab(i)

class CustomPlainTextEdit(QPlainTextEdit):

    zoomLevelChanged = pyqtSignal(float)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.defaultFontSize = self.font().pointSizeF()  # Get default font size
        self.zoomLevel = 1.0  # Default zoom level (100%)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.ZoomIn()
            else:
                self.ZoomOut()
        else:
            super().wheelEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.MiddleButton:
            self.SetZoomLevel(1)


    def ZoomIn(self):
        self.SetZoomLevel(self.zoomLevel + 0.1)

    def ZoomOut(self):
        self.SetZoomLevel(self.zoomLevel - 0.1)

    def SetZoomLevel(self, level: float):
        """Sets the zoom level with limits between 0.08 (8%) and 4.0 (400%)."""
        self.zoomLevel = max(0.08, min(4.0, level))  # Clamp between 0.08 and 4.0
        newFontSize = self.defaultFontSize * self.zoomLevel
        font = self.font()
        font.setPointSizeF(newFontSize)
        self.setFont(font)
        self.zoomLevelChanged.emit(self.zoomLevel)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            cursor = self.cursorForPosition(event.pos())
            cursor_position = cursor.position()

            text = self.toPlainText()

            # Find the start of the URL
            start = cursor_position
            while start > 0 and not text[start - 1].isspace():
                start -= 1

            # Find the end of the URL
            end = cursor_position
            while end < len(text) and not text[end].isspace():
                end += 1

            # Extract the link
            link = text[start:end]

            # Validate it using regex
            if self.IsLink(link):
                webbrowser.open(link)

        super().mousePressEvent(event)

    def IsLink(self, text):
        # Check if the text is a valid link
        parsed = urllib.parse.urlparse(text)
        return all([parsed.scheme, parsed.netloc])  # Check for scheme and netloc

class EditCommand(QUndoCommand):
    def __init__(self, editor: QPlainTextEdit, old_text: str, new_text: str):
        added_text = self.get_added_text(old_text, new_text)
        super().__init__(f"Typed '{added_text}'" if added_text else "Removed text")
        self.editor = editor
        self.old_text = old_text
        self.new_text = new_text
        self.cursor_position = self.editor.textCursor().position()  # Save cursor position

    def get_added_text(self, old_text: str, new_text: str) -> str:
        """Determine the characters that were added."""
        # Find the point where old_text and new_text differ
        if len(new_text) > len(old_text):
            return new_text[len(old_text):]  # Return the added part
        return ""  # No text added

    def undo(self):
        self.editor.blockSignals(True)  # Prevent triggering textChanged signal
        self.editor.setPlainText(self.old_text)  # Restore old text
        cur = self.editor.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.MoveAnchor)
        self.editor.setTextCursor(cur)
        self.editor.blockSignals(False)

    def redo(self):
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.new_text)  # Restore new text
        cur = self.editor.textCursor()
        cur.setPosition(self.cursor_position)  # Restore cursor position
        self.editor.setTextCursor(cur)
        self.editor.blockSignals(False)

class TabInfo:
    def __init__(self, file: str = None, encoding: str = None):
        self.Content = ""
        self.FilePath = None
        self.Modified = False
        self.CursorPos = 0
        self.IsLoading = False
        self.Encoding = None
        self.UndoStack = QUndoStack()

        if file:
            self.IsLoading = True
            self.LoadFile(file, encoding)

    def LoadFile(self, file: str, encoding: str):
        if encoding is None:
            with open(file, 'rb') as f:  # Open in binary mode to read the raw bytes
                raw_data = f.read()
                result = chardet.detect(raw_data)  # Detect encoding
                e = result['encoding']  # Get the detected encoding
        else:
            e = encoding

        with open(file, 'r', encoding=e) as f:  # Open with detected encoding
            self.Content = f.read()
        self.FilePath = file
        self.IsLoading = False
        self.Encoding = e

    def GetTitle(self):
        title = os.path.basename(self.FilePath) if self.FilePath else "Untitled"
        return title + ("*" if self.Modified else "")
    
    def Save(self):
        if not self.FilePath:
            self.SaveAs()
            return
        
        if not os.path.exists(self.FilePath):
            e = "utf-16"
        elif self.Encoding is None:
            with open(self.FilePath, 'rb') as f:  # Open in binary mode to read the raw bytes
                raw_data = f.read()
                result = chardet.detect(raw_data)  # Detect encoding
                e = result['encoding']  # Get the detected encoding
        else:
            e = self.Encoding

        with open(self.FilePath, 'w', encoding=e) as f:
            f.write(self.Content)
    
    def SaveAs(self):
        dlg = QFileDialog(None, Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.Dialog)
        dlg.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dlg.setFileMode(QFileDialog.FileMode.AnyFile)
        dlg.setNameFilter("Text files (*.txt);;All files (*.*)")
        res = dlg.exec()
        if res == QFileDialog.DialogCode.Accepted:
            self.FilePath = dlg.selectedFiles()[0]
            self.Save()

    def AskSave(self):
        if self.Modified:
            msg = QMessageBox()
            msg.setText(f"Save changes in {os.path.basename(self.FilePath) if self.FilePath else "Untitled"}?")
            msg.setWindowTitle("Unsaved Changes")
            msg.setIconPixmap(GetIconForResource("imgs", "warn.svg").pixmap(QSize(40, 40), 1.0, QIcon.Mode.Normal, QIcon.State.On))
            saveButton = msg.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
            saveAllButton = msg.addButton("Save All", QMessageBox.ButtonRole.AcceptRole)
            noSaveButton = msg.addButton("Don't Save", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            if msg.clickedButton() == saveAllButton:
                return AskSaveResult.SaveAll
            elif msg.clickedButton() == saveButton:
                return AskSaveResult.SaveCurrent
            elif msg.clickedButton() == noSaveButton:
                return AskSaveResult.NoSave
            else:
                return AskSaveResult.Cancel
        else:
            return AskSaveResult.NoSave
        
class AskSaveResult(Enum):
    SaveAll = 0,
    SaveCurrent = 1,
    NoSave = 2,
    Cancel = 3

    
class SpellCheckDialog(QDialog):
    def __init__(self, text_edit: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spell & Grammar Check")
        self.setFixedSize(400, 600)
        self.setWindowIcon(QIcon(GetResourcePath("imgs", "spgrcheck.png")))
        self.loading_dialog = None
        self.is_first_check = True

        global lang_tool
        if lang_tool is None:  # If lang_tool is still None
            self.loading_dialog = QMessageBox()
            self.loading_dialog.setWindowTitle("Loading")
            self.loading_dialog.setText("Loading Spell/Grammar checker,\nplease wait...")
            self.loading_dialog.setIconPixmap(QPixmap(GetResourcePath("imgs", "ellipsis.svg")))
            self.loading_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            self.loading_dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.loading_dialog.setStandardButtons(QMessageBox.StandardButton.NoButton)
            self.loading_dialog.show()
            lang_tool_loader.tool_ready.connect(self.StartCheck)  # Connect the signal to start the check

        self.text_edit = text_edit
        self.errors: list[language_tool_python.Match] = []
        self.current_error_index = 0

        self.error_label = QPlainTextEdit("", self)
        self.error_label.setReadOnly(True)
        self.error_label.setFixedHeight(25)
        self.suggestions_list = QListWidget(self)

        self.replace_button = QPushButton("Replace", self)
        self.replace_all_button = QPushButton("Replace All", self)
        self.ignore_button = QPushButton("Ignore", self)
        self.ignore_all_button = QPushButton("Ignore All", self)

        self.replace_button.clicked.connect(self.replace)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.ignore_button.clicked.connect(self.ignore)
        self.ignore_all_button.clicked.connect(self.ignore_all)

        self.replace_button.setEnabled(False)
        self.replace_all_button.setEnabled(False)
        self.ignore_button.setEnabled(False)
        self.ignore_all_button.setEnabled(False)

        # Layout
        button_layout = QVBoxLayout()
        button_layout.addWidget(self.replace_button)
        button_layout.addWidget(self.replace_all_button)
        button_layout.addWidget(self.ignore_button)
        button_layout.addWidget(self.ignore_all_button)
        button_layout.addStretch()

        main_layout = QVBoxLayout()
        main_layout.addWidget(self.error_label)

        lower_layout = QHBoxLayout()
        lower_layout.addWidget(self.suggestions_list)
        lower_layout.addLayout(button_layout)

        main_layout.addLayout(lower_layout)
        self.setLayout(main_layout)

        if lang_tool is not None:
            self.StartCheck()

    def StartCheck(self):
        if self.loading_dialog:
            self.loading_dialog.deleteLater()

        self.replace_button.setEnabled(True)
        self.replace_all_button.setEnabled(True)
        self.ignore_button.setEnabled(True)
        self.ignore_all_button.setEnabled(True)

        self.tool = lang_tool
        # Load initial errors from the text edit
        self.load_errors()
        self.show_next_error()

    def load_errors(self):
        text = self.text_edit.toPlainText()
        self.errors = self.tool.check(text)
        if len(self.errors) < 1 and self.is_first_check:
            if self.loading_dialog:
                self.loading_dialog.close()
            msg = QMessageBox(QMessageBox.Icon.NoIcon, "No Errors", "Spell/Grammar Check didn't find any spelling\nor grammar errors in the document.", QMessageBox.StandardButton.Ok, self)
            msg.setIconPixmap(QPixmap(GetResourcePath("imgs", "info.svg")))
            msg.exec()
            self.close()
            self.replace_button.setEnabled(False)
            self.replace_all_button.setEnabled(False)
            self.ignore_button.setEnabled(False)
            self.ignore_all_button.setEnabled(False)

    def show_next_error(self):
        if self.current_error_index < len(self.errors):
            self.is_first_check = False
            error = self.errors[self.current_error_index]
            self.error_label.setPlainText(error.matchedText)
            self.suggestions_list.clear()
            self.suggestions_list.addItems(error.replacements)
        elif not self.is_first_check:
            msg = QMessageBox(QMessageBox.Icon.NoIcon, "Reached End of Document", "Spell/Grammar Check has reached the end of the document.", QMessageBox.StandardButton.Ok, self)
            msg.setIconPixmap(QPixmap(GetResourcePath("imgs", "info.svg")))
            msg.exec()
            self.close()

    def replace(self):
        if self.suggestions_list.currentItem():
            replacement = self.suggestions_list.currentItem().text()
            self.apply_replacement(replacement)

    def replace_all(self):
        if self.suggestions_list.currentItem():
            replacement = self.suggestions_list.currentItem().text()
            rule_id = self.errors[self.current_error_index].ruleId
            
            # Keep track of the positions to be replaced
            offsets_to_replace = []
            current_text = self.text_edit.toPlainText()
            for error in self.errors:
                if error.ruleId == rule_id:
                    offsets_to_replace.append((error.offset, error.errorLength))

            # Apply replacements in reverse order to avoid shifting offsets
            for offset, length in reversed(offsets_to_replace):
                current_text = current_text[:offset] + replacement + current_text[offset + length:]

            self.text_edit.setPlainText(current_text)
            self.load_errors()  # Reload errors after replacements
            self.current_error_index = 0  # Reset the index to show the first error
            self.show_next_error()

    def ignore(self):
        self.current_error_index += 1
        self.show_next_error()

    def ignore_all(self):
        rule_id = self.errors[self.current_error_index].ruleId
        self.errors = [err for err in self.errors if err.ruleId != rule_id]
        self.show_next_error()

    def apply_replacement(self, replacement, offset=None, length=None):
        error = self.errors[self.current_error_index]
        offset = offset or error.offset
        length = length or error.errorLength

        # Update the text in the QPlainTextEdit
        current_text = self.text_edit.toPlainText()
        new_text = current_text[:offset] + replacement + current_text[offset + length:]
        self.text_edit.setPlainText(new_text)

        self.load_errors()  # Reload errors after the replacement
        self.current_error_index = 0  # Reset the index to show the first error
        self.show_next_error()

    def get_corrected_text(self):
        return self.text_edit.toPlainText()
    
class UnhidableToolbar(QToolBar):
    def contextMenuEvent(self, event):
        pass

class ZoomablePrintPreviewWidget(QPrintPreviewWidget):
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            self.setZoomMode(QPrintPreviewWidget.ZoomMode.CustomZoom)
            if delta > 0:
                self.zoomIn()
            else:
                self.zoomOut()
            self.previewChanged.emit()
            event.accept()
        else:
            super().wheelEvent(event)


class FindReplaceDialog(QDialog):
    def __init__(self, parent, editor: QPlainTextEdit, cursor: QTextCursor):
        super().__init__(parent, Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setWindowTitle("Find/Replace")
        self.setFixedSize(400, 280)
        self.setWindowIcon(GetIconForResource("imgs", "findreplace.svg"))
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self.Editor = editor  # Reference to the QPlainTextEdit editor

        self.Layout = QVBoxLayout(self)
        self.setLayout(self.Layout)

        # Layout for Find and Replace input fields
        self.InputLayout = QVBoxLayout()

        # Find Box
        self.FindBox = QLineEdit(self)
        self.FindBox.setPlaceholderText("Find...")
        self.InputLayout.addWidget(self.FindBox)
        self.InputLayout.setAlignment(self.FindBox, Qt.AlignmentFlag.AlignTop)

        # Replace Box
        self.ReplaceBox = QLineEdit(self)
        self.ReplaceBox.setPlaceholderText("Replace with...")
        self.InputLayout.addWidget(self.ReplaceBox)
        self.InputLayout.setAlignment(self.ReplaceBox, Qt.AlignmentFlag.AlignTop)
        self.InputLayout.addStretch(1)

        # Main layout for the buttons (Find Next, Replace, Replace All)
        self.ButtonsLayout = QVBoxLayout()
        
        self.FindNextButton = QPushButton(self)
        self.FindNextButton.setText("Find Next")
        self.FindNextButton.setFixedWidth(80)
        self.FindNextButton.clicked.connect(self.FindNext)  # Connect to FindNext method
        self.ButtonsLayout.addWidget(self.FindNextButton)

        self.ReplaceCurrentButton = QPushButton(self)
        self.ReplaceCurrentButton.setText("Replace")
        self.ReplaceCurrentButton.setFixedWidth(80)
        self.ReplaceCurrentButton.clicked.connect(self.ReplaceCurrent)  # Connect to ReplaceCurrent method
        self.ButtonsLayout.addWidget(self.ReplaceCurrentButton)

        self.ReplaceAllButton = QPushButton(self)
        self.ReplaceAllButton.setText("Replace All")
        self.ReplaceAllButton.setFixedWidth(80)
        self.ReplaceAllButton.clicked.connect(self.ReplaceAll)  # Connect to ReplaceAll method
        self.ButtonsLayout.addWidget(self.ReplaceAllButton)
        self.ButtonsLayout.addStretch(1)

        # Combine the Input layout and Buttons layout in a horizontal layout
        self.MainInputLayout = QHBoxLayout()
        self.MainInputLayout.addLayout(self.InputLayout)  # Add the input fields vertically
        self.MainInputLayout.addLayout(self.ButtonsLayout)  # Add buttons to the right

        self.Layout.addLayout(self.MainInputLayout)  # Add the combined layout to the main layout

        # Options group
        self.OptionsGroup = QGroupBox(self)
        self.OptionsGroup.setTitle("Options")
        self.OptionsGroupLayout = QVBoxLayout(self)
        self.OptionsGroup.setLayout(self.OptionsGroupLayout)
        self.Layout.addWidget(self.OptionsGroup)

        self.MatchCaseCheckbox = QCheckBox(self)
        self.MatchCaseCheckbox.setText("Match Case")
        self.OptionsGroupLayout.addWidget(self.MatchCaseCheckbox)

        self.MatchWordCheckbox = QCheckBox(self)
        self.MatchWordCheckbox.setText("Match Whole Word")
        self.OptionsGroupLayout.addWidget(self.MatchWordCheckbox)

        self.MatchRegExCheckbox = QCheckBox(self)
        self.MatchRegExCheckbox.setText("Use Regular Expressions (RegEx)")
        self.OptionsGroupLayout.addWidget(self.MatchRegExCheckbox)

        self.SearchLocactionLayout = QHBoxLayout(self)

        self.SearchLocactionLabel = QLabel(self)
        self.SearchLocactionLabel.setText("Search in:")
        self.SearchLocactionLayout.addWidget(self.SearchLocactionLabel)

        self.SearchLocactionCombobox = QComboBox(self)
        self.SearchLocactionCombobox.setFixedWidth(120)
        self.SearchLocactionCombobox.addItems(["Document", "Paragraph", "Current Line", "Selection"])
        if not cursor.hasSelection():
            self.SearchLocactionCombobox.removeItem(1)
            self.SearchLocactionCombobox.removeItem(1)
            self.SearchLocactionCombobox.removeItem(1)
        self.SearchLocactionLayout.addWidget(self.SearchLocactionCombobox)
        self.SearchLocactionLayout.addStretch(1)

        self.OptionsGroupLayout.addLayout(self.SearchLocactionLayout)

        self.CloseButton = QPushButton(self)
        self.CloseButton.setText("Close")
        self.CloseButton.setDefault(True)
        self.CloseButton.setFixedWidth(80)
        self.CloseButton.clicked.connect(self.close)
        self.Layout.addWidget(self.CloseButton)
        self.Layout.setAlignment(self.CloseButton, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        # Initialize the search state
        self.CurrentCursorPosition = 0
        self.Cursor = cursor

    def FindNext(self):
        """Find the next occurrence of the text in FindBox."""
        FindText = self.FindBox.text()
        if not FindText:
            return

        LocationIndex = self.SearchLocactionCombobox.currentIndex()
        if LocationIndex == 0:  # Document
            Text = self.Editor.toPlainText()
        elif LocationIndex == 1:  # Paragraph
            Text = self.Cursor.block().text()
        elif LocationIndex == 2:  # Current Line
            LineNum = self.Cursor.blockNumber()  # Get the current line number (0-based)
            Block = self.Editor.document().findBlockByNumber(LineNum)  # Get the block
            Text = Block.text()
        elif LocationIndex == 3:  # Selection
            Text = self.Cursor.selectedText()
            
        MatchCase = self.MatchCaseCheckbox.isChecked()
        MatchWholeWord = self.MatchWordCheckbox.isChecked()
        UseRegex = self.MatchRegExCheckbox.isChecked()

        # Adjust the current cursor position
        StartIndex = self.CurrentCursorPosition

        if not MatchCase:
            FindText = FindText.lower()
            Text = Text.lower()

        if UseRegex:
            pattern = FindText
            if MatchWholeWord:
                pattern = r'\b' + pattern + r'\b'  # Match whole words using word boundaries
            try:
                Match = re.search(pattern, Text[StartIndex:])
                if Match:
                    Index = StartIndex + Match.start()
                else:
                    Index = -1
            except re.error:
                Index = -1  # Invalid regex
                msg = QMessageBox(self)
                msg.setText("Please enter a valid regular expression.")
                msg.setWindowTitle("Invalid Regular Expression")
                msg.setIconPixmap(GetIconForResource("imgs", "warn.svg").pixmap(QSize(64, 64), 1.0, QIcon.Mode.Normal, QIcon.State.On))
                msg.exec()
        else:
            if MatchWholeWord:
                # Manually match whole words by checking boundaries
                Index = -1
                while StartIndex < len(Text):
                    Index = Text.find(FindText, StartIndex)
                    if Index == -1:
                        break
                    before_char = Text[Index - 1] if Index > 0 else ' '
                    after_char = Text[Index + len(FindText)] if Index + len(FindText) < len(Text) else ' '
                    if not before_char.isalnum() and not after_char.isalnum():  # Check boundaries
                        break
                    StartIndex = Index + len(FindText)
            else:
                Index = Text.find(FindText, StartIndex)

        if Index != -1:
            cursor = self.Editor.textCursor()
            cursor.setPosition(Index)  # Move cursor to the start of the found text
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, len(FindText))  # Select the found text
            self.Editor.setTextCursor(cursor)  # Update the editor with the new cursor
            self.CurrentCursorPosition = Index + len(FindText)  # Update the current cursor position
        else:
            # If not found, check if we should wrap around
            if StartIndex > 0:
                msg = QMessageBox(self)
                msg.setText("Find/Replace has reached the end of the document.\nDo you want to continue searching at the beginning of the document?")
                msg.setWindowTitle("Reached End of Document")
                msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                msg.setIconPixmap(GetIconForResource("imgs", "help.svg").pixmap(QSize(64, 64), 1.0, QIcon.Mode.Normal, QIcon.State.On))
                reply = msg.exec()
                if reply == QMessageBox.StandardButton.Yes:
                    self.CurrentCursorPosition = 0
                    self.FindNext()  # Call FindNext again to start from the beginning

    def ReplaceCurrent(self):
        """Replace the current occurrence of the text."""
        ReplaceText = self.ReplaceBox.text()
        if self.Editor.textCursor().hasSelection():
            self.Editor.textCursor().insertText(ReplaceText)

    def ReplaceAll(self):
        """Replace all occurrences of the text."""
        FindText = self.FindBox.text()
        ReplaceText = self.ReplaceBox.text()
        if not FindText:
            return

        LocationIndex = self.SearchLocactionCombobox.currentIndex()
        if LocationIndex == 0:  # Document
            Text = self.Editor.toPlainText()
        elif LocationIndex == 1:  # Paragraph
            Text = self.Cursor.block().text()
        elif LocationIndex == 2:  # Current Line
            LineNum = self.Cursor.blockNumber()  # Get the current line number (0-based)
            Block = self.Editor.document().findBlockByNumber(LineNum)  # Get the block
            Text = Block.text()
        elif LocationIndex == 3:  # Selection
            Text = self.Cursor.selectedText()

        MatchCase = self.MatchCaseCheckbox.isChecked()
        MatchWholeWord = self.MatchWordCheckbox.isChecked()
        UseRegex = self.MatchRegExCheckbox.isChecked()

        if not MatchCase:
            FindText = FindText.lower()
            Text = Text.lower()

        if UseRegex:
            pattern = FindText
            if MatchWholeWord:
                pattern = r'\b' + pattern + r'\b'  # Match whole words using word boundaries
            try:
                NewText = re.sub(pattern, ReplaceText, Text, flags=re.IGNORECASE if not MatchCase else 0)
            except re.error:
                return  # Invalid regex, skip replacement
        else:
            if MatchWholeWord:
                # Manually replace whole words by checking boundaries
                NewText = Text
                StartIndex = 0
                while StartIndex < len(NewText):
                    Index = NewText.find(FindText, StartIndex)
                    if Index == -1:
                        break
                    before_char = NewText[Index - 1] if Index > 0 else ' '
                    after_char = NewText[Index + len(FindText)] if Index + len(FindText) < len(NewText) else ' '
                    if not before_char.isalnum() and not after_char.isalnum():  # Check boundaries
                        NewText = NewText[:Index] + ReplaceText + NewText[Index + len(FindText):]
                        StartIndex = Index + len(ReplaceText)
                    else:
                        StartIndex = Index + len(FindText)
            else:
                NewText = Text.replace(FindText, ReplaceText)

        self.Editor.setPlainText(NewText)

        # Reset the search state after replacing all
        self.CurrentCursorPosition = 0

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
