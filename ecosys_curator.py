import wx
import wx.grid
try:
    import wx.lib.agw.aui as aui
except ImportError:
    print("Warning: Advanced AUI not available, using basic layout")
    aui = None
import requests
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
import os
import threading
from datetime import datetime
import zipfile
import io
try:
    from PIL import Image
except ImportError:
    print("Warning: PIL not available, image display disabled")
    Image = None
import base64

class EcosysAPICurator(wx.Frame):
    def __init__(self):
        super().__init__(None, title="EcoSIS API Data Curator", size=(1400, 900))
        
        # Initialize variables
        self.api_data = []
        self.filtered_data = []
        self.current_selection = None
        self.download_progress = 0
        
        self.init_ui()
        self.setup_api_config()
        
    def init_ui(self):
        """Initialize the user interface with AUI manager or basic layout"""
        if aui:
            self._mgr = aui.AuiManager(self)
        else:
            self._mgr = None
        
        # Create menu bar
        self.create_menu_bar()
        
        # Create main panels
        self.create_api_panel()
        self.create_data_grid()
        self.create_spectral_panel()
        self.create_metadata_panel()
        self.create_download_panel()
        
        # Setup layout
        if self._mgr:
            self.setup_aui_panes()
        else:
            self.setup_basic_layout()
        
        # Create status bar
        self.CreateStatusBar()
        self.SetStatusText("Ready")
        
        if self._mgr:
            self._mgr.Update()
        
    def create_menu_bar(self):
        """Create menu bar with file, view, and tools menus"""
        menubar = wx.MenuBar()
        
        # File menu
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_OPEN, "&Open Config\tCtrl+O", "Open API configuration")
        file_menu.Append(wx.ID_SAVE, "&Save Data\tCtrl+S", "Save current data")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tCtrl+Q", "Exit application")
        
        # View menu
        view_menu = wx.Menu()
        view_menu.Append(101, "&Refresh Data\tF5", "Refresh API data")
        view_menu.Append(102, "&Clear Cache", "Clear cached data")
        
        # Tools menu
        tools_menu = wx.Menu()
        tools_menu.Append(201, "&Batch Download", "Download all selected datasets")
        tools_menu.Append(202, "&Export Metadata", "Export metadata to CSV")
        tools_menu.Append(203, "&API Settings", "Configure API endpoints")
        
        menubar.Append(file_menu, "&File")
        menubar.Append(view_menu, "&View")
        menubar.Append(tools_menu, "&Tools")
        
        self.SetMenuBar(menubar)
        
        # Bind menu events
        self.Bind(wx.EVT_MENU, self.on_exit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.on_refresh, id=101)
        self.Bind(wx.EVT_MENU, self.on_batch_download, id=201)
        self.Bind(wx.EVT_MENU, self.on_api_settings, id=203)
        
    def create_api_panel(self):
        """Create API connection and search panel"""
        self.api_panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # API endpoint configuration
        api_box = wx.StaticBox(self.api_panel, label="API Configuration")
        api_sizer = wx.StaticBoxSizer(api_box, wx.VERTICAL)
        
        # Environment selection (Production vs Dev)
        env_sizer = wx.BoxSizer(wx.HORIZONTAL)
        env_sizer.Add(wx.StaticText(self.api_panel, label="Environment:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.env_choice = wx.Choice(self.api_panel, choices=["Production (ecosis.org)", "Developer (dev-search.ecospectra.org)"])
        self.env_choice.SetSelection(0)
        self.env_choice.Bind(wx.EVT_CHOICE, self.on_env_change)
        env_sizer.Add(self.env_choice, 0, wx.ALL, 5)
        api_sizer.Add(env_sizer, 0, wx.EXPAND)
        
        # Base URL
        url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        url_sizer.Add(wx.StaticText(self.api_panel, label="Base URL:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.url_text = wx.TextCtrl(self.api_panel, value="https://ecosis.org", size=(300, -1))
        url_sizer.Add(self.url_text, 1, wx.EXPAND|wx.ALL, 5)
        api_sizer.Add(url_sizer, 0, wx.EXPAND)
        
        # Connect button and refresh
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.connect_btn = wx.Button(self.api_panel, label="Connect & Load Data")
        self.connect_btn.Bind(wx.EVT_BUTTON, self.on_connect)
        button_sizer.Add(self.connect_btn, 1, wx.EXPAND|wx.ALL, 5)
        
        self.refresh_btn = wx.Button(self.api_panel, label="Refresh")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        button_sizer.Add(self.refresh_btn, 0, wx.ALL, 5)
        
        api_sizer.Add(button_sizer, 0, wx.EXPAND)
        
        # Debug: Add a simple test to make sure button works
        def test_button_click(event):
            print("Button clicked - event handler working!")
            self.on_connect(event)
        
        # Temporarily bind test handler to debug
        # self.connect_btn.Bind(wx.EVT_BUTTON, test_button_click)
        
        sizer.Add(api_sizer, 0, wx.EXPAND|wx.ALL, 5)
        
        # Search and filter section
        search_box = wx.StaticBox(self.api_panel, label="Search & Filter")
        search_sizer = wx.StaticBoxSizer(search_box, wx.VERTICAL)
        
        # Search text with timer for delayed filtering
        search_text_sizer = wx.BoxSizer(wx.HORIZONTAL)
        search_text_sizer.Add(wx.StaticText(self.api_panel, label="Search:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.search_text = wx.TextCtrl(self.api_panel, size=(250, -1))
        self.search_text.Bind(wx.EVT_TEXT, self.on_search_text)
        search_text_sizer.Add(self.search_text, 1, wx.EXPAND|wx.ALL, 5)
        search_sizer.Add(search_text_sizer, 0, wx.EXPAND)
        
        # Dataset type filter - updated for actual EcoSIS themes
        type_sizer = wx.BoxSizer(wx.HORIZONTAL)
        type_sizer.Add(wx.StaticText(self.api_panel, label="Theme:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.type_choice = wx.Choice(self.api_panel, choices=["All", "ecology", "forest", "physiology", "phenology", "leaf", "canopy", "soil", "water", "agriculture"])
        self.type_choice.Bind(wx.EVT_CHOICE, self.on_filter_change)
        type_sizer.Add(self.type_choice, 0, wx.ALL, 5)
        search_sizer.Add(type_sizer, 0, wx.EXPAND)
        
        # Organization filter - now using combobox
        org_sizer = wx.BoxSizer(wx.HORIZONTAL)
        org_sizer.Add(wx.StaticText(self.api_panel, label="Organization:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.org_choice = wx.ComboBox(self.api_panel, size=(200, -1), style=wx.CB_DROPDOWN)
        self.org_choice.Bind(wx.EVT_COMBOBOX, self.on_filter_change)
        # Use EVT_TEXT_ENTER or timer to avoid filtering on every keystroke
        self.org_choice.Bind(wx.EVT_TEXT_ENTER, self.on_filter_change)
        org_sizer.Add(self.org_choice, 0, wx.ALL, 5)
        search_sizer.Add(org_sizer, 0, wx.EXPAND)
        
        # Date range filter (using text controls for better compatibility)
        date_sizer = wx.BoxSizer(wx.HORIZONTAL)
        date_sizer.Add(wx.StaticText(self.api_panel, label="Date From:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.date_from = wx.TextCtrl(self.api_panel, size=(100, -1), value="")
        self.date_from.SetToolTip("Format: YYYY-MM-DD (optional)")
        date_sizer.Add(self.date_from, 0, wx.ALL, 5)
        date_sizer.Add(wx.StaticText(self.api_panel, label="To:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.date_to = wx.TextCtrl(self.api_panel, size=(100, -1), value="")
        self.date_to.SetToolTip("Format: YYYY-MM-DD (optional)")
        date_sizer.Add(self.date_to, 0, wx.ALL, 5)
        search_sizer.Add(date_sizer, 0, wx.EXPAND)
        
        # Pagination controls
        page_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.prev_btn = wx.Button(self.api_panel, label="◀ Previous", size=(80, -1))
        self.prev_btn.Bind(wx.EVT_BUTTON, self.on_prev_page)
        self.prev_btn.Enable(False)
        page_sizer.Add(self.prev_btn, 0, wx.ALL, 5)
        
        self.page_info = wx.StaticText(self.api_panel, label="Page 1 of 1")
        page_sizer.Add(self.page_info, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        
        self.next_btn = wx.Button(self.api_panel, label="Next ▶", size=(80, -1))
        self.next_btn.Bind(wx.EVT_BUTTON, self.on_next_page)
        self.next_btn.Enable(False)
        page_sizer.Add(self.next_btn, 0, wx.ALL, 5)
        
        search_sizer.Add(page_sizer, 0, wx.EXPAND)
        
        sizer.Add(search_sizer, 1, wx.EXPAND|wx.ALL, 5)
        
        self.api_panel.SetSizer(sizer)
        
    def create_data_grid(self):
        """Create main data grid for displaying API results"""
        self.data_panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Grid for displaying datasets with checkbox column
        self.data_grid = wx.grid.Grid(self.data_panel)
        self.data_grid.CreateGrid(0, 8)  # Added checkbox column (8 columns total)
        
        # Set column headers for EcoSIS data (added checkbox column)
        headers = ["Download", "ID", "Title", "Organization", "Spectra Count", "Keywords", "Theme", "Status"]
        for i, header in enumerate(headers):
            self.data_grid.SetColLabelValue(i, header)
            
        # Adjust column sizes (added checkbox column)
        self.data_grid.SetColSize(0, 80)   # Download checkbox
        self.data_grid.SetColSize(1, 80)   # ID
        self.data_grid.SetColSize(2, 230)  # Title (adjusted)
        self.data_grid.SetColSize(3, 160)  # Organization (adjusted)
        self.data_grid.SetColSize(4, 100)  # Spectra Count
        self.data_grid.SetColSize(5, 230)  # Keywords (adjusted)
        self.data_grid.SetColSize(6, 120)  # Theme
        self.data_grid.SetColSize(7, 80)   # Status
        
        self.data_grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.on_grid_select)
        self.data_grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.on_grid_cell_click)
        
        # Set up checkbox column
        checkbox_attr = wx.grid.GridCellAttr()
        checkbox_attr.SetEditor(wx.grid.GridCellBoolEditor())
        checkbox_attr.SetRenderer(wx.grid.GridCellBoolRenderer())
        self.data_grid.SetColAttr(0, checkbox_attr)
        
        sizer.Add(self.data_grid, 1, wx.EXPAND|wx.ALL, 5)
        
        # Selection info
        self.selection_info = wx.StaticText(self.data_panel, label="No dataset selected")
        sizer.Add(self.selection_info, 0, wx.ALL, 5)
        
        self.data_panel.SetSizer(sizer)
        
    def create_spectral_panel(self):
        """Create spectral analysis and visualization panel"""
        self.spectral_panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Matplotlib figure for spectral curves with responsive sizing
        # Start with a reasonable default size that will be adjusted
        self.spectral_figure = Figure(figsize=(6, 4), tight_layout=True, dpi=100)
        
        # Check for dark mode
        if wx.SystemSettings.GetAppearance().IsDark():
            self.spectral_figure.patch.set_facecolor('#2b2b2b')
            plt.style.use('dark_background')
        
        self.spectral_canvas = FigureCanvas(self.spectral_panel, -1, self.spectral_figure)
        self.spectral_axes = self.spectral_figure.add_subplot(111)
        
        # Configure initial plot appearance
        self.configure_spectral_plot()
        
        # Initialize with placeholder plot to establish dimensions
        self.initialize_spectral_plot()
        
        sizer.Add(self.spectral_canvas, 1, wx.EXPAND|wx.ALL, 5)
        
        # Spectral analysis controls
        controls_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.load_spectral_btn = wx.Button(self.spectral_panel, label="Load Spectral Data")
        self.load_spectral_btn.Bind(wx.EVT_BUTTON, self.on_load_spectral)
        controls_sizer.Add(self.load_spectral_btn, 0, wx.ALL, 5)
        
        self.export_plot_btn = wx.Button(self.spectral_panel, label="Export Plot")
        self.export_plot_btn.Bind(wx.EVT_BUTTON, self.on_export_plot)
        controls_sizer.Add(self.export_plot_btn, 0, wx.ALL, 5)
        
        # Spectral indices calculation
        self.calc_indices_btn = wx.Button(self.spectral_panel, label="Calculate Indices")
        self.calc_indices_btn.Bind(wx.EVT_BUTTON, self.on_calculate_indices)
        controls_sizer.Add(self.calc_indices_btn, 0, wx.ALL, 5)
        
        sizer.Add(controls_sizer, 0, wx.EXPAND|wx.ALL, 5)
        
        self.spectral_panel.SetSizer(sizer)
        
        # Bind resize event for responsive plotting
        self.spectral_panel.Bind(wx.EVT_SIZE, self.on_spectral_panel_resize)
        
    def configure_spectral_plot(self):
        """Configure spectral plot appearance"""
        # Check for dark mode and configure accordingly
        if wx.SystemSettings.GetAppearance().IsDark():
            # Dark mode colors
            self.spectral_axes.set_facecolor('#1e1e1e')
            self.spectral_axes.tick_params(colors='white')
            self.spectral_axes.xaxis.label.set_color('white')
            self.spectral_axes.yaxis.label.set_color('white')
            self.spectral_axes.title.set_color('white')
            self.spectral_axes.spines['bottom'].set_color('white')
            self.spectral_axes.spines['top'].set_color('white')
            self.spectral_axes.spines['right'].set_color('white')
            self.spectral_axes.spines['left'].set_color('white')
        
        self.spectral_axes.set_title("Spectral Reflectance Curves")
        self.spectral_axes.set_xlabel("Wavelength (nm)")
        self.spectral_axes.set_ylabel("Reflectance")
        self.spectral_axes.grid(True, alpha=0.3)
        
    def initialize_spectral_plot(self):
        """Initialize spectral plot with placeholder content and proper sizing"""
        # Create a simple placeholder plot to establish dimensions
        wavelengths = [400, 500, 600, 700, 800, 900]
        placeholder = [0.1, 0.2, 0.15, 0.3, 0.6, 0.4]
        
        self.spectral_axes.plot(wavelengths, placeholder, '--', alpha=0.3, label='No data loaded')
        self.spectral_axes.set_xlim(300, 2500)
        self.spectral_axes.set_ylim(0, 1)
        self.spectral_axes.legend()
        
        # Force initial layout calculation
        self.spectral_figure.tight_layout()
        
        # Use CallAfter to ensure proper sizing after window is fully constructed
        wx.CallAfter(self.initial_plot_resize)
        
    def initial_plot_resize(self):
        """Perform initial plot resize after window construction"""
        if hasattr(self, 'spectral_canvas'):
            # Get the actual canvas size
            canvas_size = self.spectral_canvas.GetSize()
            
            if canvas_size.width > 10 and canvas_size.height > 10:  # Ensure valid size
                # Convert to inches (matplotlib uses inches, wx uses pixels)
                dpi = self.spectral_figure.dpi
                fig_width = canvas_size.width / dpi
                fig_height = canvas_size.height / dpi
                
                # Set figure size to match canvas
                self.spectral_figure.set_size_inches(fig_width, fig_height)
                self.spectral_figure.tight_layout()
                self.spectral_canvas.draw()
            else:
                # If size isn't ready, try again in a moment
                wx.CallAfter(self.initial_plot_resize)
        
    def on_spectral_panel_resize(self, event):
        """Handle spectral panel resize events with timer to avoid excessive redraws"""
        # Stop previous timer if running
        if self.resize_timer.IsRunning():
            self.resize_timer.Stop()
        
        # Start timer for 150ms delay (only redraw after user stops resizing)
        self.resize_timer.Start(150, wx.TIMER_ONE_SHOT)
        event.Skip()
        
    def on_resize_timer(self, event):
        """Called when resize timer expires - perform the actual plot resize"""
        self.refresh_spectral_plot()
        
    def refresh_spectral_plot(self):
        """Refresh spectral plot with current dimensions using cached data"""
        if hasattr(self, 'spectral_figure') and hasattr(self, 'spectral_canvas'):
            # Get current canvas size
            canvas_size = self.spectral_canvas.GetSize()
            
            if canvas_size.width > 10 and canvas_size.height > 10:
                # Update figure size to match canvas
                dpi = self.spectral_figure.dpi
                fig_width = canvas_size.width / dpi
                fig_height = canvas_size.height / dpi
                
                self.spectral_figure.set_size_inches(fig_width, fig_height)
                
                # If we have cached spectral data, replot it efficiently
                if self.cached_spectral_data:
                    self.plot_cached_spectral_data()
                else:
                    # Just apply layout for placeholder or empty plot
                    self.spectral_figure.tight_layout()
                    self.spectral_canvas.draw()
        
    def create_metadata_panel(self):
        """Create metadata display and photo viewer panel"""
        self.metadata_panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Notebook for metadata and photos
        self.metadata_notebook = wx.Notebook(self.metadata_panel)
        
        # Metadata page
        self.metadata_page = wx.Panel(self.metadata_notebook)
        metadata_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.metadata_text = wx.TextCtrl(self.metadata_page, style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.metadata_text.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        metadata_sizer.Add(self.metadata_text, 1, wx.EXPAND|wx.ALL, 5)
        
        self.metadata_page.SetSizer(metadata_sizer)
        self.metadata_notebook.AddPage(self.metadata_page, "Metadata")
        
        # Photos page
        self.photos_page = wx.Panel(self.metadata_notebook)
        photos_sizer = wx.BoxSizer(wx.VERTICAL)
        
        self.photo_panel = wx.Panel(self.photos_page)
        self.photo_sizer = wx.BoxSizer(wx.VERTICAL)
        self.photo_panel.SetSizer(self.photo_sizer)
        
        photos_sizer.Add(self.photo_panel, 1, wx.EXPAND|wx.ALL, 5)
        
        # Photo controls
        photo_controls = wx.BoxSizer(wx.HORIZONTAL)
        self.load_photos_btn = wx.Button(self.photos_page, label="Load Photos")
        self.load_photos_btn.Bind(wx.EVT_BUTTON, self.on_load_photos)
        photo_controls.Add(self.load_photos_btn, 0, wx.ALL, 5)
        
        photos_sizer.Add(photo_controls, 0, wx.EXPAND|wx.ALL, 5)
        
        self.photos_page.SetSizer(photos_sizer)
        self.metadata_notebook.AddPage(self.photos_page, "Photos")
        
        sizer.Add(self.metadata_notebook, 1, wx.EXPAND|wx.ALL, 5)
        self.metadata_panel.SetSizer(sizer)
        
    def create_download_panel(self):
        """Create download management panel"""
        self.download_panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Download queue
        queue_box = wx.StaticBox(self.download_panel, label="Download Queue")
        queue_sizer = wx.StaticBoxSizer(queue_box, wx.VERTICAL)
        
        self.download_list = wx.ListCtrl(self.download_panel, style=wx.LC_REPORT)
        self.download_list.AppendColumn("Dataset", width=200)
        self.download_list.AppendColumn("Status", width=100)
        self.download_list.AppendColumn("Progress", width=100)
        self.download_list.AppendColumn("Size", width=80)
        
        queue_sizer.Add(self.download_list, 1, wx.EXPAND|wx.ALL, 5)
        
        # Download controls
        download_controls = wx.BoxSizer(wx.HORIZONTAL)
        
        self.add_download_btn = wx.Button(self.download_panel, label="Add Selected")
        self.add_download_btn.Bind(wx.EVT_BUTTON, self.on_add_download)
        download_controls.Add(self.add_download_btn, 0, wx.ALL, 5)
        
        self.start_download_btn = wx.Button(self.download_panel, label="Start Downloads")
        self.start_download_btn.Bind(wx.EVT_BUTTON, self.on_start_downloads)
        download_controls.Add(self.start_download_btn, 0, wx.ALL, 5)
        
        self.pause_download_btn = wx.Button(self.download_panel, label="Pause")
        self.pause_download_btn.Bind(wx.EVT_BUTTON, self.on_pause_downloads)
        download_controls.Add(self.pause_download_btn, 0, wx.ALL, 5)
        
        self.clear_queue_btn = wx.Button(self.download_panel, label="Clear Queue")
        self.clear_queue_btn.Bind(wx.EVT_BUTTON, self.on_clear_queue)
        download_controls.Add(self.clear_queue_btn, 0, wx.ALL, 5)
        
        queue_sizer.Add(download_controls, 0, wx.EXPAND|wx.ALL, 5)
        
        # Progress bar
        self.download_progress_bar = wx.Gauge(self.download_panel, range=100)
        queue_sizer.Add(self.download_progress_bar, 0, wx.EXPAND|wx.ALL, 5)
        
        sizer.Add(queue_sizer, 1, wx.EXPAND|wx.ALL, 5)
        
        # Download location
        location_sizer = wx.BoxSizer(wx.HORIZONTAL)
        location_sizer.Add(wx.StaticText(self.download_panel, label="Download to:"), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        self.download_path = wx.TextCtrl(self.download_panel, value=os.path.expanduser("~/Downloads/EcoSISData"))
        location_sizer.Add(self.download_path, 1, wx.EXPAND|wx.ALL, 5)
        
        self.browse_path_btn = wx.Button(self.download_panel, label="Browse...")
        self.browse_path_btn.Bind(wx.EVT_BUTTON, self.on_browse_path)
        location_sizer.Add(self.browse_path_btn, 0, wx.ALL, 5)
        
        sizer.Add(location_sizer, 0, wx.EXPAND|wx.ALL, 5)
        
        self.download_panel.SetSizer(sizer)
        
    def setup_basic_layout(self):
        """Setup basic sizer layout when AUI is not available"""
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # Left panel for API controls
        main_sizer.Add(self.api_panel, 0, wx.EXPAND|wx.ALL, 5)
        
        # Center/right panel
        center_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Data grid
        center_sizer.Add(self.data_panel, 2, wx.EXPAND|wx.ALL, 5)
        
        # Bottom panels in horizontal layout
        bottom_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bottom_sizer.Add(self.spectral_panel, 1, wx.EXPAND|wx.ALL, 5)
        bottom_sizer.Add(self.metadata_panel, 1, wx.EXPAND|wx.ALL, 5)
        
        center_sizer.Add(bottom_sizer, 1, wx.EXPAND)
        center_sizer.Add(self.download_panel, 0, wx.EXPAND|wx.ALL, 5)
        
        main_sizer.Add(center_sizer, 1, wx.EXPAND)
        
        self.SetSizer(main_sizer)
        
    def setup_aui_panes(self):
        """Setup AUI pane layout"""
        if not self._mgr:
            return
            
        # Left pane - API controls
        self._mgr.AddPane(self.api_panel, aui.AuiPaneInfo().
                         Name("api_panel").Caption("API & Search").
                         Left().Layer(1).Position(1).
                         CloseButton(False).MaximizeButton(True).
                         BestSize((350, -1)))
        
        # Center pane - Data grid
        self._mgr.AddPane(self.data_panel, aui.AuiPaneInfo().
                         Name("data_panel").Caption("Dataset Browser").
                         Center().Layer(0).
                         CloseButton(False).MaximizeButton(True))
        
        # Right top pane - Spectral analysis
        self._mgr.AddPane(self.spectral_panel, aui.AuiPaneInfo().
                         Name("spectral_panel").Caption("Spectral Analysis").
                         Right().Layer(1).Position(1).
                         CloseButton(False).MaximizeButton(True).
                         BestSize((400, 350)))
        
        # Right middle pane - Metadata
        self._mgr.AddPane(self.metadata_panel, aui.AuiPaneInfo().
                         Name("metadata_panel").Caption("Metadata & Photos").
                         Right().Layer(1).Position(2).
                         CloseButton(False).MaximizeButton(True).
                         BestSize((400, 250)))
        
        # Bottom pane - Downloads
        self._mgr.AddPane(self.download_panel, aui.AuiPaneInfo().
                         Name("download_panel").Caption("Download Manager").
                         Bottom().Layer(1).Position(1).
                         CloseButton(False).MaximizeButton(True).
                         BestSize((-1, 200)))
        
    def setup_api_config(self):
        """Setup default API configuration"""
        # Set default EcoSIS API URL
        self.url_text.SetValue("https://ecosis.org")
        
        # Load saved configuration if exists
        config_file = "ecosys_config.json"
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    self.url_text.SetValue(config.get('base_url', 'https://ecosis.org'))
                    self.download_path.SetValue(config.get('download_path', os.path.expanduser("~/Downloads/EcoSISData")))
            except:
                pass
        
        # Initialize API parameters
        self.current_page = 0
        self.page_size = 20
        self.total_datasets = 0
        self.all_organizations = set()  # Store unique organizations
        self.all_themes = set()  # Store unique themes
        
        # Search timer to prevent too frequent filtering
        self.search_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_search_timer, self.search_timer)
        
        # Resize timer to prevent too frequent plot updates
        self.resize_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_resize_timer, self.resize_timer)
        
        # Cache for spectral data to avoid reprocessing on resize
        self.cached_spectral_data = None
        
        # Track which datasets are available locally
        self.local_datasets = set()
        
        # Check for existing local data
        self.check_local_data()
                
    def save_config(self):
        """Save current API configuration"""
        config = {
            'base_url': self.url_text.GetValue(),
            'download_path': self.download_path.GetValue(),
            'environment': self.env_choice.GetSelection()
        }
        try:
            with open("ecosys_config.json", 'w') as f:
                json.dump(config, f, indent=2)
        except:
            pass
    
    def on_env_change(self, event):
        """Handle environment selection change"""
        selection = self.env_choice.GetSelection()
        if selection == 0:  # Production
            self.url_text.SetValue("https://ecosis.org")
        else:  # Developer
            self.url_text.SetValue("http://dev-search.ecospectra.org")
    
    def on_prev_page(self, event):
        """Handle previous page navigation"""
        if self.current_page > 0:
            self.current_page -= 1
            self.load_api_data()
            
    def on_next_page(self, event):
        """Handle next page navigation"""
        total_pages = (self.total_datasets + self.page_size - 1) // self.page_size
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.load_api_data()
            
    def update_pagination_controls(self):
        """Update pagination button states and info"""
        total_pages = max(1, (self.total_datasets + self.page_size - 1) // self.page_size)
        current_display_page = self.current_page + 1
        
        self.prev_btn.Enable(self.current_page > 0)
        self.next_btn.Enable(self.current_page < total_pages - 1)
        self.page_info.SetLabel(f"Page {current_display_page} of {total_pages}")
    
    def build_filters(self):
        """Build EcoSIS API filters based on current UI state"""
        filters = []
        
        # Theme filter (instead of Category)
        theme = self.type_choice.GetStringSelection()
        if theme and theme != "All":
            filters.append({"Theme": theme})
        
        # Organization filter - now using ComboBox
        organization = self.org_choice.GetValue().strip()
        if organization:
            filters.append({"Organization": {"$regex": organization, "$options": "i"}})
        
        # Date filters (if provided)
        date_from = self.date_from.GetValue().strip()
        date_to = self.date_to.GetValue().strip()
        
        if date_from or date_to:
            date_filter = {}
            if date_from:
                try:
                    # Validate date format
                    from datetime import datetime
                    datetime.strptime(date_from, '%Y-%m-%d')
                    date_filter["$gte"] = date_from
                except ValueError:
                    pass  # Skip invalid date
                    
            if date_to:
                try:
                    from datetime import datetime
                    datetime.strptime(date_to, '%Y-%m-%d')
                    date_filter["$lte"] = date_to
                except ValueError:
                    pass  # Skip invalid date
            
            if date_filter:
                filters.append({"date": date_filter})
            
        return filters

    # Event handlers
    def on_connect(self, event):
        """Connect to API and load initial data"""
        self.SetStatusText("Connecting to EcoSIS API...")
        self.current_page = 0
        # Use threading to avoid blocking UI
        wx.CallAfter(self.load_api_data_threaded)
        
    def load_api_data_threaded(self):
        """Load API data in a separate thread to avoid blocking UI"""
        loading_thread = threading.Thread(target=self.load_api_data)
        loading_thread.daemon = True
        loading_thread.start()
        
    def load_api_data(self):
        """Load data from EcoSIS API"""
        try:
            base_url = self.url_text.GetValue().rstrip('/')
            search_text = self.search_text.GetValue()
            filters = self.build_filters()
            
            # Calculate pagination
            start_idx = self.current_page * self.page_size
            stop_idx = start_idx + self.page_size
            
            # Build API URL for package search
            api_url = f"{base_url}/api/package/search"
            
            # Prepare query parameters
            params = {
                'text': search_text,
                'filters': json.dumps(filters) if filters else '[]',
                'start': start_idx,
                'stop': stop_idx
            }
            
            # Make API request
            response = requests.get(api_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Update data
                self.api_data = data.get('items', [])
                self.filtered_data = self.api_data.copy()
                self.total_datasets = data.get('total', 0)
                
                # Collect organizations for the combobox
                self.collect_organizations()
                
                # Collect themes for the combobox
                self.collect_themes()
                
                # Update UI
                wx.CallAfter(self.update_data_grid)
                wx.CallAfter(self.update_pagination_controls)
                wx.CallAfter(self.update_organization_combobox)
                wx.CallAfter(self.update_theme_combobox)
                wx.CallAfter(self.SetStatusText, f"Loaded {len(self.api_data)} datasets (Total: {self.total_datasets})")
                
                # Store additional filters for future use
                self.additional_filters = data.get('filters', {})
                
            else:
                wx.CallAfter(self.SetStatusText, f"API Error: HTTP {response.status_code}")
                
        except requests.RequestException as e:
            wx.CallAfter(self.SetStatusText, f"Connection error: {str(e)}")
        except Exception as e:
            wx.CallAfter(self.SetStatusText, f"Error: {str(e)}")
            
    def update_data_grid(self):
        """Update the data grid with current EcoSIS data including checkboxes and highlighting"""
        # Clear existing data
        if self.data_grid.GetNumberRows() > 0:
            self.data_grid.DeleteRows(0, self.data_grid.GetNumberRows())
            
        # Add new data
        for i, dataset in enumerate(self.filtered_data):
            self.data_grid.AppendRows(1)
            
            # Extract EcoSIS-specific data
            ecosis_info = dataset.get('ecosis', {})
            
            # Column 0: Download checkbox
            is_local = self.is_dataset_local(dataset)
            self.data_grid.SetCellValue(i, 0, "1" if is_local else "0")
            
            # Column 1: ID
            self.data_grid.SetCellValue(i, 1, str(dataset.get('_id', '')))
            
            # Column 2: Title - use ecosis.package_title or title
            title = ecosis_info.get('package_title', '')
            if not title:
                title = ecosis_info.get('title', '')
            if not title:
                # Fallback to package_id if both are missing
                title = ecosis_info.get('package_id', 'Unknown')
            self.data_grid.SetCellValue(i, 2, str(title))
            
            # Column 3: Organization - handle both string and list properly
            organization = ecosis_info.get('organization', [])
            if isinstance(organization, list):
                # Join list elements properly
                org_str = ', '.join(str(org) for org in organization if org)
            elif isinstance(organization, str):
                org_str = organization
            else:
                org_str = 'Unknown'
            self.data_grid.SetCellValue(i, 3, org_str)
            
            # Column 4: Spectra count
            spectra_count = ecosis_info.get('spectra_count', 0)
            self.data_grid.SetCellValue(i, 4, str(spectra_count))
            
            # Column 5: Keywords - use Keywords from main dataset
            keywords = dataset.get('Keywords', [])
            if not keywords:
                # Fallback to ecosis.keyword if main Keywords is empty
                keywords = ecosis_info.get('keyword', [])
            
            if isinstance(keywords, list):
                keywords_str = ', '.join(str(kw) for kw in keywords[:3] if kw)  # Show first 3 keywords
                if len(keywords) > 3:
                    keywords_str += f'... ({len(keywords)} total)'
            elif isinstance(keywords, str):
                keywords_str = keywords
            else:
                keywords_str = ''
            self.data_grid.SetCellValue(i, 5, keywords_str)
            
            # Column 6: Theme - use Theme from main dataset
            theme_list = dataset.get('Theme', [])
            if isinstance(theme_list, list):
                theme_str = ', '.join(str(t) for t in theme_list[:2] if t)  # Show first 2 themes
            elif isinstance(theme_list, str):
                theme_str = theme_list
            else:
                # Fallback to Category if Theme is not available
                category_list = dataset.get('Category', [])
                if isinstance(category_list, list):
                    theme_str = ', '.join(str(c) for c in category_list[:2] if c)
                elif isinstance(category_list, str):
                    theme_str = category_list
                else:
                    theme_str = ''
            self.data_grid.SetCellValue(i, 6, theme_str)
            
            # Column 7: Status
            status = "Downloaded" if is_local else "Available"
            self.data_grid.SetCellValue(i, 7, status)
            
            # Highlight row if data is available locally
            if is_local:
                self.highlight_local_row(i)
        
    def check_local_data(self):
        """Check which datasets' spectral JSON files are available locally - WITH DEBUG"""
        download_path = self.download_path.GetValue()
        print(f"DEBUG: check_local_data - Scanning directory: {download_path}")
        
        if not os.path.exists(download_path):
            print("DEBUG: check_local_data - Download directory does not exist")
            return
            
        self.local_datasets = set()  # Reset the set
        
        try:
            files_found = []
            for filename in os.listdir(download_path):
                if filename.startswith('spectra_') and filename.endswith('.json'):
                    files_found.append(filename)
                    
                    # Extract dataset name from filename (remove spectra_ prefix and .json extension)
                    dataset_name = filename[8:-5]  # Remove 'spectra_' and '.json'
                    
                    print(f"DEBUG: check_local_data - Found file: {filename}")
                    print(f"DEBUG: check_local_data - Extracted name: {dataset_name}")
                    
                    # Store both the clean filename version and various title variations
                    self.local_datasets.add(dataset_name)
                    
                    # Convert underscores back to spaces for matching
                    dataset_name_spaced = dataset_name.replace('_', ' ')
                    self.local_datasets.add(dataset_name_spaced)
                    
                    # Also store the original filename without extension for exact matching
                    self.local_datasets.add(filename[:-5])  # Remove just .json
            
            print(f"DEBUG: check_local_data - Found {len(files_found)} spectral JSON files")
            print(f"DEBUG: check_local_data - Files: {files_found}")
            print(f"DEBUG: check_local_data - Tracked dataset variations: {len(self.local_datasets)}")
            
        except OSError as e:
            print(f"DEBUG: check_local_data - Error scanning directory: {e}")
        
    def on_grid_cell_click(self, event):
        """Handle grid cell clicks, especially for checkbox column - WITH DEBUG"""
        row = event.GetRow()
        col = event.GetCol()
        
        print(f"DEBUG: Grid cell clicked - Row: {row}, Col: {col}")
        
        if col == 0:  # Checkbox column
            if 0 <= row < len(self.filtered_data):
                dataset = self.filtered_data[row]
                current_value = self.data_grid.GetCellValue(row, col)
                
                print(f"DEBUG: Checkbox clicked - Current value: {current_value}")
                print(f"DEBUG: Dataset title: {dataset.get('ecosis', {}).get('package_title', 'Unknown')}")
                
                if current_value == "1":
                    # Unchecking - user wants to remove local data (optional feature)
                    print("DEBUG: Unchecking checkbox - no action taken")
                    pass  # For now, just allow unchecking
                else:
                    # Checking - user wants to download
                    print("DEBUG: Checking checkbox - initiating download")
                    self.download_single_dataset(dataset, row)
        else:
            # For other columns, handle normal selection
            if 0 <= row < len(self.filtered_data):
                dataset = self.filtered_data[row]
                self.current_selection = dataset
                
                print(f"DEBUG: Selected dataset: {dataset.get('ecosis', {}).get('package_title', 'Unknown')}")
                print(f"DEBUG: Dataset ID: {dataset.get('_id', 'Unknown')}")
                
                # Check if local data exists
                is_local = self.is_dataset_local(dataset)
                print(f"DEBUG: Is dataset local? {is_local}")
                
                self.update_metadata_display()
                title = self.current_selection.get('ecosis', {}).get('package_title', 'Unknown')
                self.selection_info.SetLabel(f"Selected: {title}")
        
        event.Skip()
        
    def download_single_dataset(self, dataset, row):
        """Download complete spectral data in JSON format when checkbox is clicked"""
        title = dataset.get('ecosis', {}).get('package_title', 'Unknown')
        dataset_id = dataset.get('_id')
        
        if not dataset_id:
            wx.MessageBox("Dataset ID not found", "Error", wx.OK | wx.ICON_ERROR)
            return
            
        # Update UI to show downloading
        self.data_grid.SetCellValue(row, 7, "Downloading...")  # Status column
        
        # Start download in thread
        download_thread = threading.Thread(target=self.download_spectral_json_worker, 
                                         args=(dataset_id, title, row))
        download_thread.daemon = True
        download_thread.start()
        
    def normalize_filename(self, title):
        """Normalize dataset title for consistent filename generation"""
        print(f"DEBUG: normalize_filename - Input title: '{title}'")
        
        # Replace problematic characters consistently
        clean_title = title.replace(' ', '_').replace('/', '_').replace('\\', '_')
        
        print(f"DEBUG: normalize_filename - Output title: '{clean_title}'")
        return clean_title
    
    def download_spectral_json_worker(self, dataset_id, title, row):
        """Worker thread for downloading complete spectral data in JSON format"""
        try:
            base_url = self.url_text.GetValue().rstrip('/')
            download_path = self.download_path.GetValue()
            os.makedirs(download_path, exist_ok=True)
            
            # Use consistent filename normalization
            clean_title = self.normalize_filename(title)
            filename = f"spectra_{clean_title}.json"
            filepath = os.path.join(download_path, filename)
            
            print(f"DEBUG: download_spectral_json_worker - Title: '{title}'")
            print(f"DEBUG: download_spectral_json_worker - Clean title: '{clean_title}'")
            print(f"DEBUG: download_spectral_json_worker - Filename: '{filename}'")
            print(f"DEBUG: download_spectral_json_worker - Full path: '{filepath}'")
            
            # Download all spectra in blocks of 10
            all_spectra = []
            block_size = 10
            start = 0
            total_downloaded = 0
            
            wx.CallAfter(self.SetStatusText, f"Downloading spectra for: {title}")
            
            while True:
                # Get spectra block using EcoSIS API
                spectra_url = f"{base_url}/api/spectra/search/{dataset_id}"
                params = {
                    'start': start,
                    'stop': start + block_size,
                    'filters': '[]'
                }
                
                response = requests.get(spectra_url, params=params, timeout=60)
                
                if response.status_code == 200:
                    spectra_data = response.json()
                    items = spectra_data.get('items', [])
                    
                    if not items:
                        break  # No more spectra to download
                    
                    all_spectra.extend(items)
                    total_downloaded += len(items)
                    start += block_size
                    
                    # Update progress
                    wx.CallAfter(self.data_grid.SetCellValue, row, 7, f"Downloaded {total_downloaded}")
                    wx.CallAfter(self.SetStatusText, f"Downloaded {total_downloaded} spectra for: {title}")
                    
                    # If we got fewer items than requested, we've reached the end
                    if len(items) < block_size:
                        break
                        
                else:
                    wx.CallAfter(self.data_grid.SetCellValue, row, 7, f"Error: HTTP {response.status_code}")
                    return
            
            if all_spectra:
                # Create comprehensive JSON structure
                complete_data = {
                    'dataset_info': {
                        'id': dataset_id,
                        'title': title,
                        'download_date': datetime.now().isoformat(),
                        'total_spectra': len(all_spectra),
                        'source': 'EcoSIS API'
                    },
                    'spectra': all_spectra
                }
                
                # Save JSON file
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(complete_data, f, indent=2)
                
                print(f"DEBUG: download_spectral_json_worker - Saved {len(all_spectra)} spectra to {filepath}")
                
                # IMPORTANT: Update local datasets tracking immediately after successful download
                wx.CallAfter(self.check_local_data)  # Refresh the local datasets list
                
                # Update UI
                wx.CallAfter(self.data_grid.SetCellValue, row, 0, "1")  # Check the checkbox
                wx.CallAfter(self.data_grid.SetCellValue, row, 7, f"Complete ({total_downloaded})")
                wx.CallAfter(self.highlight_local_row, row)
                wx.CallAfter(self.SetStatusText, f"Downloaded {total_downloaded} spectra: {title}")
                
            else:
                wx.CallAfter(self.data_grid.SetCellValue, row, 7, "No spectra found")
                
        except Exception as e:
            error_msg = f"Error: {str(e)[:20]}"
            wx.CallAfter(self.data_grid.SetCellValue, row, 7, error_msg)
            wx.CallAfter(self.SetStatusText, f"Download failed: {title}")
            
    def is_dataset_local(self, dataset):
        """Check if a dataset's spectral JSON is available locally - FIXED VERSION"""
        if not dataset:
            print("DEBUG: is_dataset_local - No dataset provided")
            return False
            
        download_path = self.download_path.GetValue()
        title = dataset.get('ecosis', {}).get('package_title', '')
        
        print(f"DEBUG: is_dataset_local - Checking for: '{title}'")
        print(f"DEBUG: is_dataset_local - Download path: {download_path}")
        
        if not title:
            print("DEBUG: is_dataset_local - No title found")
            return False
            
        # Use consistent filename normalization
        clean_title = self.normalize_filename(title)
        filename = f"spectra_{clean_title}.json"
        filepath = os.path.join(download_path, filename)
        
        print(f"DEBUG: is_dataset_local - Looking for file: {filepath}")
        
        # Check what files actually exist
        try:
            existing_files = [f for f in os.listdir(download_path) if f.startswith('spectra_') and f.endswith('.json')]
            print(f"DEBUG: is_dataset_local - Existing files: {existing_files}")
            
            # Check for exact match first
            if filename in existing_files:
                print(f"DEBUG: is_dataset_local - Exact match found!")
                file_size = os.path.getsize(filepath)
                print(f"DEBUG: is_dataset_local - File size: {file_size} bytes")
                return file_size > 100
            
            # Check for case variations or other close matches
            for existing_file in existing_files:
                if existing_file.lower() == filename.lower():
                    print(f"DEBUG: is_dataset_local - Case-insensitive match found: {existing_file}")
                    alt_filepath = os.path.join(download_path, existing_file)
                    file_size = os.path.getsize(alt_filepath)
                    print(f"DEBUG: is_dataset_local - File size: {file_size} bytes")
                    return file_size > 100
                    
        except OSError as e:
            print(f"DEBUG: is_dataset_local - Error listing directory: {e}")
        
        print(f"DEBUG: is_dataset_local - No matching file found")
        return False
        
    def load_spectral_data_local(self, dataset):
        """Load spectral data from local JSON file - FIXED VERSION"""
        print("DEBUG: load_spectral_data_local - METHOD CALLED!")
        
        try:
            download_path = self.download_path.GetValue()
            title = dataset.get('ecosis', {}).get('package_title', 'Unknown')
            
            # Use consistent filename normalization
            clean_title = self.normalize_filename(title)
            filename = f"spectra_{clean_title}.json"
            filepath = os.path.join(download_path, filename)
            
            print(f"DEBUG: load_spectral_data_local - Title: '{title}'")
            print(f"DEBUG: load_spectral_data_local - Full path: '{filepath}'")
            
            # List existing files for debugging and find actual file
            actual_filepath = None
            try:
                existing_files = [f for f in os.listdir(download_path) if f.startswith('spectra_') and f.endswith('.json')]
                print(f"DEBUG: load_spectral_data_local - Existing files: {existing_files}")
                
                # Try exact match first
                if filename in existing_files:
                    actual_filepath = filepath
                    print(f"DEBUG: load_spectral_data_local - Exact match found")
                else:
                    # Try case-insensitive match
                    for existing_file in existing_files:
                        if existing_file.lower() == filename.lower():
                            actual_filepath = os.path.join(download_path, existing_file)
                            print(f"DEBUG: load_spectral_data_local - Case-insensitive match found: {existing_file}")
                            break
                            
            except OSError as e:
                print(f"DEBUG: load_spectral_data_local - Error listing directory: {e}")
            
            if not actual_filepath or not os.path.exists(actual_filepath):
                print(f"DEBUG: load_spectral_data_local - File does not exist")
                return False
                
            print(f"DEBUG: load_spectral_data_local - Using file: {actual_filepath}")
            
            # Check file size first
            file_size = os.path.getsize(actual_filepath)
            print(f"DEBUG: load_spectral_data_local - File size: {file_size} bytes")
            
            if file_size < 100:
                print("DEBUG: load_spectral_data_local - File appears to be empty or too small")
                return False
                
            # Read JSON file
            print("DEBUG: load_spectral_data_local - About to read JSON file...")
            with open(actual_filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"DEBUG: load_spectral_data_local - JSON loaded successfully")
            print(f"DEBUG: load_spectral_data_local - JSON keys: {list(data.keys())}")
            
            if 'spectra' in data:
                spectra_count = len(data['spectra'])
                print(f"DEBUG: load_spectral_data_local - Found {spectra_count} spectra in JSON")
                
                # Show first spectrum structure
                if spectra_count > 0:
                    first_spectrum = data['spectra'][0]
                    print(f"DEBUG: load_spectral_data_local - First spectrum keys: {list(first_spectrum.keys())}")
                    if 'datapoints' in first_spectrum:
                        datapoints = first_spectrum['datapoints']
                        sample_keys = list(datapoints.keys())[:5]
                        print(f"DEBUG: load_spectral_data_local - First spectrum sample wavelengths: {sample_keys}")
                        print(f"DEBUG: load_spectral_data_local - Total datapoints in first spectrum: {len(datapoints)}")
                    else:
                        print("DEBUG: load_spectral_data_local - First spectrum has no 'datapoints' key")
            else:
                print("DEBUG: load_spectral_data_local - No 'spectra' key in JSON")
                print(f"DEBUG: load_spectral_data_local - Available keys: {list(data.keys())}")
            
            if 'dataset_info' in data:
                dataset_info = data['dataset_info']
                print(f"DEBUG: load_spectral_data_local - Dataset info: {dataset_info}")
            
            # Process local JSON data into spectral format
            print("DEBUG: load_spectral_data_local - About to process JSON data...")
            spectral_data = self.process_local_json_data(data, title)
            
            print(f"DEBUG: load_spectral_data_local - Processed {len(spectral_data)} spectra")
            
            if spectral_data:
                print("DEBUG: load_spectral_data_local - Spectral data found, caching and plotting...")
                
                # Cache the local data
                self.cached_spectral_data = spectral_data
                
                # Plot the cached data
                print("DEBUG: load_spectral_data_local - About to plot cached data...")
                self.plot_cached_spectral_data()
                
                total_spectra = data.get('dataset_info', {}).get('total_spectra', len(spectral_data))
                status_msg = f"Loaded {len(spectral_data)} of {total_spectra} spectra from local file"
                print(f"DEBUG: load_spectral_data_local - Setting status: {status_msg}")
                self.SetStatusText(status_msg)
                print(f"DEBUG: load_spectral_data_local - Successfully loaded and plotted data")
                return True
            else:
                print("DEBUG: load_spectral_data_local - No spectral data found after processing")
                wx.MessageBox("No spectral data found in local file", "No Data", wx.OK | wx.ICON_WARNING)
                return False
                
        except json.JSONDecodeError as e:
            print(f"DEBUG: load_spectral_data_local - JSON decode error: {str(e)}")
            wx.MessageBox(f"Invalid JSON file: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            return False
        except FileNotFoundError as e:
            print(f"DEBUG: load_spectral_data_local - File not found: {str(e)}")
            wx.MessageBox(f"File not found: {str(e)}", "Error", xx.OK | wx.ICON_ERROR)
            return False
        except Exception as e:
            print(f"DEBUG: load_spectral_data_local - Exception occurred: {str(e)}")
            import traceback
            print(f"DEBUG: load_spectral_data_local - Full traceback:")
            traceback.print_exc()
            wx.MessageBox(f"Error loading local data: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            return False
            
    # Also ensure process_local_json_data has proper debug
    def process_local_json_data(self, data, title):
        """Process local JSON data into spectral format - WITH ENHANCED DEBUG"""
        print("DEBUG: process_local_json_data - METHOD CALLED!")
        spectral_data = []
        
        try:
            spectra_items = data.get('spectra', [])
            print(f"DEBUG: process_local_json_data - Processing {len(spectra_items)} spectra items")
            
            if not spectra_items:
                print("DEBUG: process_local_json_data - No spectra items found in data")
                return []
            
            # Process up to 15 spectra for visualization
            for i, spectrum in enumerate(spectra_items[:15]):
                print(f"DEBUG: process_local_json_data - Processing spectrum {i+1}")
                
                if not isinstance(spectrum, dict):
                    print(f"DEBUG: process_local_json_data - Spectrum {i+1} is not a dict: {type(spectrum)}")
                    continue
                    
                datapoints = spectrum.get('datapoints', {})
                print(f"DEBUG: process_local_json_data - Spectrum {i+1} has {len(datapoints)} datapoints")
                
                if not datapoints:
                    print(f"DEBUG: process_local_json_data - Spectrum {i+1} has no datapoints")
                    continue
                
                # Show a sample of the datapoints structure
                sample_keys = list(datapoints.keys())[:5]
                sample_values = [datapoints[k] for k in sample_keys]
                print(f"DEBUG: process_local_json_data - Sample datapoints: {dict(zip(sample_keys, sample_values))}")
                
                # Separate wavelengths from other metadata
                spectrum_wavelengths = []
                spectrum_reflectance = []
                
                numeric_keys_found = 0
                for key, value in datapoints.items():
                    try:
                        # Check if key looks like a wavelength (numeric)
                        wavelength = float(key)
                        if 300 <= wavelength <= 2500:  # Typical spectral range
                            spectrum_wavelengths.append(wavelength)
                            
                            # Handle various value formats
                            if isinstance(value, (int, float)):
                                refl_value = float(value)
                            else:
                                refl_value = float(str(value))
                            spectrum_reflectance.append(refl_value)
                            numeric_keys_found += 1
                            
                    except (ValueError, TypeError) as e:
                        # This is normal for non-wavelength keys, don't spam debug
                        if i == 0 and numeric_keys_found < 5:  # Only show first few for first spectrum
                            print(f"DEBUG: process_local_json_data - Skipping non-numeric key '{key}': {e}")
                        continue
                
                print(f"DEBUG: process_local_json_data - Spectrum {i+1} has {len(spectrum_wavelengths)} valid wavelength points")
                
                if spectrum_wavelengths and spectrum_reflectance:
                    # Show wavelength range
                    wl_min, wl_max = min(spectrum_wavelengths), max(spectrum_wavelengths)
                    refl_min, refl_max = min(spectrum_reflectance), max(spectrum_reflectance)
                    print(f"DEBUG: process_local_json_data - Spectrum {i+1} wavelength range: {wl_min}-{wl_max}nm")
                    print(f"DEBUG: process_local_json_data - Spectrum {i+1} reflectance range: {refl_min:.3f}-{refl_max:.3f}")
                    
                    # Sort by wavelength
                    sorted_data = sorted(zip(spectrum_wavelengths, spectrum_reflectance))
                    if sorted_data:
                        wavelengths, reflectance = zip(*sorted_data)
                        
                        # Create meaningful legend label
                        label = self.create_spectrum_label(spectrum, i + 1)
                        print(f"DEBUG: process_local_json_data - Spectrum {i+1} label: '{label}'")
                        
                        spectral_data.append({
                            'wavelengths': wavelengths,
                            'reflectance': reflectance,
                            'label': label,
                            'color_index': len(spectral_data)
                        })
                        
                        print(f"DEBUG: process_local_json_data - Successfully added spectrum {i+1}")
                else:
                    print(f"DEBUG: process_local_json_data - Spectrum {i+1} has no valid wavelength/reflectance data")
                        
        except Exception as e:
            print(f"DEBUG: process_local_json_data - Exception: {e}")
            import traceback
            traceback.print_exc()
            return []
            
        print(f"DEBUG: process_local_json_data - Returning {len(spectral_data)} processed spectra")
        return spectral_data
          
    def highlight_local_row(self, row):
        """Highlight a row that has local data available with dark mode support"""
        # Check for dark mode and use appropriate colors
        if wx.SystemSettings.GetAppearance().IsDark():
            # Dark mode: subtle dark blue highlight
            highlight_color = wx.Colour(45, 55, 80)  # Dark blue-gray
        else:
            # Light mode: light blue highlight
            highlight_color = wx.Colour(230, 240, 255)  # Light blue
            
        # Set background color for all columns in the row
        for col in range(self.data_grid.GetNumberCols()):
            self.data_grid.SetCellBackgroundColour(row, col, highlight_color)
        
        self.data_grid.Refresh()
        
    def load_spectral_data_local(self, dataset):
        """Load spectral data from local CSV file"""
        try:
            download_path = self.download_path.GetValue()
            title = dataset.get('ecosis', {}).get('package_title', 'Unknown')
            filename = f"{title.replace(' ', '_').replace('/', '_')}.csv"
            filepath = os.path.join(download_path, filename)
            
            if not os.path.exists(filepath):
                return False
                
            # Read CSV file
            import pandas as pd
            df = pd.read_csv(filepath)
            
            # Process local CSV data into spectral format
            spectral_data = self.process_local_csv_data(df, title)
            
            if spectral_data:
                # Cache the local data
                self.cached_spectral_data = spectral_data
                
                # Plot the cached data
                self.plot_cached_spectral_data()
                
                self.SetStatusText(f"Loaded {len(spectral_data)} spectra from local file")
                return True
            else:
                wx.MessageBox("No spectral data found in local file", "No Data", wx.OK | wx.ICON_WARNING)
                return False
                
        except Exception as e:
            wx.MessageBox(f"Error loading local data: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            return False
            
    def process_local_csv_data(self, df, title):
        """Process local CSV data into spectral format"""
        spectral_data = []
        
        try:
            # Look for wavelength columns (numeric column names between 300-2500)
            wavelength_cols = []
            for col in df.columns:
                try:
                    wl = float(col)
                    if 300 <= wl <= 2500:
                        wavelength_cols.append(col)
                except ValueError:
                    continue
                    
            if not wavelength_cols:
                return []
                
            wavelength_cols.sort(key=float)  # Sort by wavelength
            
            # Process up to 5 rows as different spectra
            for idx, (_, row) in enumerate(df.head(5).iterrows()):
                wavelengths = []
                reflectance = []
                
                for wl_col in wavelength_cols:
                    try:
                        wl = float(wl_col)
                        refl = float(row[wl_col])
                        if not pd.isna(refl):
                            wavelengths.append(wl)
                            reflectance.append(refl)
                    except (ValueError, TypeError):
                        continue
                        
                if wavelengths and reflectance:
                    # Create label from metadata columns
                    label = f"Local S{idx+1}"
                    
                    # Try to get meaningful labels from non-wavelength columns
                    for col in ['Scientific Name', 'Common Name', 'Sample ID', 'ID']:
                        if col in df.columns and pd.notna(row.get(col)):
                            label = f"S{idx+1}: {row[col]}"
                            break
                    
                    spectral_data.append({
                        'wavelengths': wavelengths,
                        'reflectance': reflectance,
                        'label': label,
                        'color_index': len(spectral_data)
                    })
                    
        except Exception as e:
            print(f"Error processing local CSV: {e}")
            return []
            
        return spectral_data
        
    def collect_organizations(self):
        """Collect unique organizations from current dataset"""
        for dataset in self.api_data:
            ecosis_info = dataset.get('ecosis', {})
            organization = ecosis_info.get('organization', [])
            
            if isinstance(organization, list):
                for org in organization:
                    if org and str(org).strip():
                        self.all_organizations.add(str(org).strip())
            elif isinstance(organization, str) and organization.strip():
                self.all_organizations.add(organization.strip())
    
    def collect_themes(self):
        """Collect unique themes from current dataset"""
        for dataset in self.api_data:
            theme_list = dataset.get('Theme', [])
            if isinstance(theme_list, list):
                for theme in theme_list:
                    if theme and str(theme).strip():
                        self.all_themes.add(str(theme).strip())
            elif isinstance(theme_list, str) and theme_list.strip():
                self.all_themes.add(theme_list.strip())
                
            # Also collect from Category field
            category_list = dataset.get('Category', [])
            if isinstance(category_list, list):
                for category in category_list:
                    if category and str(category).strip():
                        self.all_themes.add(str(category).strip())
            elif isinstance(category_list, str) and category_list.strip():
                self.all_themes.add(category_list.strip())
                
    def update_organization_combobox(self):
        """Update organization combobox with collected organizations"""
        # Clear existing items
        self.org_choice.Clear()
        
        # Add "All" option
        self.org_choice.Append("All")
        
        # Add sorted organizations
        sorted_orgs = sorted(list(self.all_organizations))
        for org in sorted_orgs:
            self.org_choice.Append(org)
        
        # Set to "All" by default
        self.org_choice.SetSelection(0)
        
    def update_theme_combobox(self):
        """Update theme combobox with collected themes"""
        # Get current selection
        current_selection = self.type_choice.GetStringSelection()
        
        # Clear existing items
        self.type_choice.Clear()
        
        # Add "All" option
        self.type_choice.Append("All")
        
        # Add sorted themes
        sorted_themes = sorted(list(self.all_themes))
        for theme in sorted_themes:
            self.type_choice.Append(theme)
        
        # Try to restore previous selection, otherwise set to "All"
        if current_selection and current_selection in sorted_themes:
            self.type_choice.SetStringSelection(current_selection)
        else:
            self.type_choice.SetSelection(0)  # "All"
        """Load spectral data from local CSV file"""
        try:
            download_path = self.download_path.GetValue()
            title = dataset.get('ecosis', {}).get('package_title', 'Unknown')
            filename = f"{title.replace(' ', '_').replace('/', '_')}.csv"
            filepath = os.path.join(download_path, filename)
            
            if not os.path.exists(filepath):
                return False
                
            # Read CSV file
            import pandas as pd
            df = pd.read_csv(filepath)
            
            # Process local CSV data into spectral format
            spectral_data = self.process_local_csv_data(df, title)
            
            if spectral_data:
                # Cache the local data
                self.cached_spectral_data = spectral_data
                
                # Plot the cached data
                self.plot_cached_spectral_data()
                
                self.SetStatusText(f"Loaded {len(spectral_data)} spectra from local file")
                return True
            else:
                wx.MessageBox("No spectral data found in local file", "No Data", wx.OK | wx.ICON_WARNING)
                return False
                
        except Exception as e:
            wx.MessageBox(f"Error loading local data: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
            return False
            
    def process_local_csv_data(self, df, title):
        """Process local CSV data into spectral format"""
        spectral_data = []
        
        try:
            # Look for wavelength columns (numeric column names between 300-2500)
            wavelength_cols = []
            for col in df.columns:
                try:
                    wl = float(col)
                    if 300 <= wl <= 2500:
                        wavelength_cols.append(col)
                except ValueError:
                    continue
                    
            if not wavelength_cols:
                return []
                
            wavelength_cols.sort(key=float)  # Sort by wavelength
            
            # Process up to 5 rows as different spectra
            for idx, (_, row) in enumerate(df.head(5).iterrows()):
                wavelengths = []
                reflectance = []
                
                for wl_col in wavelength_cols:
                    try:
                        wl = float(wl_col)
                        refl = float(row[wl_col])
                        if not pd.isna(refl):
                            wavelengths.append(wl)
                            reflectance.append(refl)
                    except (ValueError, TypeError):
                        continue
                        
                if wavelengths and reflectance:
                    # Create label from metadata columns
                    label = f"Local S{idx+1}"
                    
                    # Try to get meaningful labels from non-wavelength columns
                    for col in ['Scientific Name', 'Common Name', 'Sample ID', 'ID']:
                        if col in df.columns and pd.notna(row.get(col)):
                            label = f"S{idx+1}: {row[col]}"
                            break
                    
                    spectral_data.append({
                        'wavelengths': wavelengths,
                        'reflectance': reflectance,
                        'label': label,
                        'color_index': len(spectral_data)
                    })
                    
        except Exception as e:
            print(f"Error processing local CSV: {e}")
            return []
            
        return spectral_data
        """Collect unique organizations from current dataset"""
        for dataset in self.api_data:
            ecosis_info = dataset.get('ecosis', {})
            organization = ecosis_info.get('organization', [])
            
            if isinstance(organization, list):
                for org in organization:
                    if org and str(org).strip():
                        self.all_organizations.add(str(org).strip())
            elif isinstance(organization, str) and organization.strip():
                self.all_organizations.add(organization.strip())
    
    def collect_themes(self):
        """Collect unique themes from current dataset"""
        for dataset in self.api_data:
            theme_list = dataset.get('Theme', [])
            if isinstance(theme_list, list):
                for theme in theme_list:
                    if theme and str(theme).strip():
                        self.all_themes.add(str(theme).strip())
            elif isinstance(theme_list, str) and theme_list.strip():
                self.all_themes.add(theme_list.strip())
                
            # Also collect from Category field
            category_list = dataset.get('Category', [])
            if isinstance(category_list, list):
                for category in category_list:
                    if category and str(category).strip():
                        self.all_themes.add(str(category).strip())
            elif isinstance(category_list, str) and category_list.strip():
                self.all_themes.add(category_list.strip())
                
    def update_theme_combobox(self):
        """Update theme combobox with collected themes"""
        # Get current selection
        current_selection = self.type_choice.GetStringSelection()
        
        # Clear existing items
        self.type_choice.Clear()
        
        # Add "All" option
        self.type_choice.Append("All")
        
        # Add sorted themes
        sorted_themes = sorted(list(self.all_themes))
        for theme in sorted_themes:
            self.type_choice.Append(theme)
        
        # Try to restore previous selection, otherwise set to "All"
        if current_selection and current_selection in sorted_themes:
            self.type_choice.SetStringSelection(current_selection)
        else:
            self.type_choice.SetSelection(0)  # "All"
                
    def update_organization_combobox(self):
        """Update organization combobox with collected organizations"""
        # Clear existing items
        self.org_choice.Clear()
        
        # Add "All" option
        self.org_choice.Append("All")
        
        # Add sorted organizations
        sorted_orgs = sorted(list(self.all_organizations))
        for org in sorted_orgs:
            self.org_choice.Append(org)
        
        # Set to "All" by default
        self.org_choice.SetSelection(0)
        
    def on_grid_select(self, event):
        """Handle grid row selection"""
        row = event.GetRow()
        if 0 <= row < len(self.filtered_data):
            self.current_selection = self.filtered_data[row]
            self.update_metadata_display()
            self.selection_info.SetLabel(f"Selected: {self.current_selection.get('ecosis', {}).get('package_title', 'Unknown')}")
            
    def update_metadata_display(self):
        """Update metadata display for selected EcoSIS dataset"""
        if not self.current_selection:
            return
            
        # Format metadata for EcoSIS dataset
        metadata_text = "EcoSIS Dataset Metadata:\n\n"
        
        # Dataset ID and basic info
        metadata_text += f"Dataset ID: {self.current_selection.get('_id', 'Unknown')}\n\n"
        
        # EcoSIS-specific information
        ecosis_info = self.current_selection.get('ecosis', {})
        if ecosis_info:
            metadata_text += "Dataset Information:\n"
            for key, value in ecosis_info.items():
                if isinstance(value, list):
                    value_str = ', '.join(str(v) for v in value)
                else:
                    value_str = str(value)
                metadata_text += f"  {key.title().replace('_', ' ')}: {value_str}\n"
            metadata_text += "\n"
        
        # Dataset attributes (spectral metadata)
        metadata_text += "Spectral Attributes:\n"
        for key, value in self.current_selection.items():
            if key not in ['_id', 'ecosis'] and value:
                if isinstance(value, list):
                    if len(value) <= 5:
                        value_str = ', '.join(str(v) for v in value)
                    else:
                        value_str = f"{', '.join(str(v) for v in value[:5])}... ({len(value)} total)"
                else:
                    value_str = str(value)
                metadata_text += f"  {key.title().replace('_', ' ')}: {value_str}\n"
                
        self.metadata_text.SetValue(metadata_text)
        
    def on_search_text(self, event):
        """Handle search text changes with timer to avoid too frequent updates"""
        # Stop previous timer if running
        if self.search_timer.IsRunning():
            self.search_timer.Stop()
        
        # Start timer for 300ms delay
        self.search_timer.Start(300, wx.TIMER_ONE_SHOT)
    
    def on_search_timer(self, event):
        """Called when search timer expires - perform the actual search"""
        self.apply_local_filters()
    
    def on_search(self, event):
        """Handle immediate search (for other triggers)"""
        # Use local filtering for instant results
        self.apply_local_filters()
        
    def on_filter_change(self, event):
        """Handle filter changes"""
        # Use local filtering for instant results
        self.apply_local_filters()
        
    def apply_filters(self):
        """Apply current search and filter settings using API (for new data loads)"""
        # This is used when loading new data from API with server-side filtering
        self.current_page = 0
        self.load_api_data()
        
    def apply_local_filters(self):
        """Apply current search and filter settings locally for instant results"""
        search_term = self.search_text.GetValue().lower()
        theme_filter = self.type_choice.GetStringSelection()
        org_filter = self.org_choice.GetValue().strip().lower()
        
        self.filtered_data = []
        
        for dataset in self.api_data:
            # Apply search filter - search in title, keywords, and other text fields
            if search_term:
                ecosis_info = dataset.get('ecosis', {})
                title = ecosis_info.get('package_title', '').lower()
                keywords = dataset.get('Keywords', [])
                if isinstance(keywords, list):
                    keywords_str = ' '.join(str(kw) for kw in keywords).lower()
                else:
                    keywords_str = str(keywords).lower()
                
                # Search in title, keywords, and organization
                organization = ecosis_info.get('organization', [])
                if isinstance(organization, list):
                    org_str = ' '.join(str(org) for org in organization).lower()
                else:
                    org_str = str(organization).lower()
                
                # Check if search term is found in any of these fields
                if (search_term not in title and 
                    search_term not in keywords_str and 
                    search_term not in org_str):
                    continue
            
            # Apply theme filter - simplified exact matching
            if theme_filter and theme_filter != "All":
                theme_list = dataset.get('Theme', [])
                category_list = dataset.get('Category', [])
                theme_match = False
                
                # Check if the selected theme appears in the Theme list
                if isinstance(theme_list, list):
                    theme_match = theme_filter in theme_list
                elif isinstance(theme_list, str):
                    theme_match = theme_filter == theme_list
                
                # Also check Category list if Theme didn't match
                if not theme_match and isinstance(category_list, list):
                    theme_match = theme_filter in category_list
                elif not theme_match and isinstance(category_list, str):
                    theme_match = theme_filter == category_list
                
                if not theme_match:
                    continue
            
            # Apply organization filter
            if org_filter and org_filter != "all":
                ecosis_info = dataset.get('ecosis', {})
                organization = ecosis_info.get('organization', [])
                if isinstance(organization, list):
                    org_match = any(org_filter in str(org).lower() for org in organization)
                elif isinstance(organization, str):
                    org_match = org_filter in organization.lower()
                else:
                    org_match = False
                    
                if not org_match:
                    continue
            
            self.filtered_data.append(dataset)
        
        # Update the grid with filtered results
        wx.CallAfter(self.update_data_grid)
        wx.CallAfter(self.SetStatusText, f"Showing {len(self.filtered_data)} of {len(self.api_data)} datasets")
        
    def on_load_spectral(self, event):
        """Load and display spectral data for selected dataset - WITH DEBUG"""
        print("DEBUG: Load spectral button clicked")
        
        if not self.current_selection:
            print("DEBUG: No dataset selected")
            wx.MessageBox("Please select a dataset first", "No Selection", wx.OK | wx.ICON_WARNING)
            return
        
        dataset_title = self.current_selection.get('ecosis', {}).get('package_title', 'Unknown')
        dataset_id = self.current_selection.get('_id', 'Unknown')
        print(f"DEBUG: Loading spectral data for: {dataset_title}")
        print(f"DEBUG: Dataset ID: {dataset_id}")
        
        self.load_spectral_data()
        
    def load_spectral_data(self):
        """Load spectral data from local file if available, otherwise from EcoSIS API - WITH DEBUG"""
        if not self.current_selection:
            print("DEBUG: No current selection in load_spectral_data")
            wx.MessageBox("Please select a dataset first", "No Selection", wx.OK | wx.ICON_WARNING)
            return
        
        dataset_title = self.current_selection.get('ecosis', {}).get('package_title', 'Unknown')
        print(f"DEBUG: load_spectral_data called for: {dataset_title}")
        
        # Check if data is available locally first
        is_local = self.is_dataset_local(self.current_selection)
        print(f"DEBUG: Dataset is local: {is_local}")
        
        if is_local:
            print("DEBUG: Attempting to load from local file")
            success = self.load_spectral_data_local(self.current_selection)
            print(f"DEBUG: Local loading success: {success}")
            if success:
                return  # Successfully loaded from local file
            else:
                print("DEBUG: Local loading failed, will try API")
        else:
            print("DEBUG: Dataset not available locally, will try API")
            
        # Fallback to API if local loading failed or not available
        print("DEBUG: Falling back to API loading")
        self.load_spectral_data_api()
        
    def load_spectral_data_api(self):
        """Load spectral data from EcoSIS API"""
        try:
            base_url = self.url_text.GetValue().rstrip('/')
            dataset_id = self.current_selection.get('_id')
            
            if not dataset_id:
                wx.MessageBox("Dataset ID not found", "Error", wx.OK | wx.ICON_ERROR)
                return
            
            # Get spectra data using EcoSIS API
            spectra_url = f"{base_url}/api/spectra/search/{dataset_id}"
            params = {
                'start': 0,
                'stop': 10,  # Limit to first 10 spectra for performance
                'filters': '[]'
            }
            
            response = requests.get(spectra_url, params=params, timeout=30)
            
            if response.status_code == 200:
                spectra_data = response.json()
                items = spectra_data.get('items', [])
                
                if not items:
                    wx.MessageBox("No spectral data found for this dataset", "No Data", wx.OK | wx.ICON_WARNING)
                    return
                
                # Process and cache spectral data
                self.cached_spectral_data = self.process_spectral_data(items)
                
                # Plot the cached data
                self.plot_cached_spectral_data()
                
                self.SetStatusText(f"Loaded {len(self.cached_spectral_data)} spectra from API")
                
            else:
                wx.MessageBox(f"API Error: HTTP {response.status_code}", "Error", wx.OK | wx.ICON_ERROR)
                
        except requests.RequestException as e:
            wx.MessageBox(f"Network error: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
        except Exception as e:
            wx.MessageBox(f"Error loading spectral data: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
    
    def process_spectral_data(self, items):
        """Process raw spectral data and cache it for efficient reuse"""
        processed_spectra = []
        
        for i, spectrum in enumerate(items[:5]):  # Limit to 5 spectra for clarity
            datapoints = spectrum.get('datapoints', {})
            
            # Separate wavelengths from other metadata
            spectrum_wavelengths = []
            spectrum_reflectance = []
            
            for key, value in datapoints.items():
                try:
                    # Check if key looks like a wavelength (numeric)
                    wavelength = float(key)
                    if 300 <= wavelength <= 2500:  # Typical spectral range
                        spectrum_wavelengths.append(wavelength)
                        spectrum_reflectance.append(float(str(value)))  # Convert to float safely
                except (ValueError, TypeError):
                    continue  # Skip non-numeric keys (metadata)
            
            if spectrum_wavelengths and spectrum_reflectance:
                # Sort by wavelength
                sorted_data = sorted(zip(spectrum_wavelengths, spectrum_reflectance))
                if sorted_data:
                    wavelengths, reflectance = zip(*sorted_data)
                    
                    # Create meaningful legend label
                    label = self.create_spectrum_label(spectrum, i + 1)
                    
                    # Store processed data
                    processed_spectra.append({
                        'wavelengths': wavelengths,
                        'reflectance': reflectance,
                        'label': label,
                        'color_index': len(processed_spectra)
                    })
        
        return processed_spectra
    
    def plot_cached_spectral_data(self):
        """Plot spectral data from cache - efficient for redraws"""
        if not self.cached_spectral_data:
            return
        
        # Clear previous plots
        self.spectral_axes.clear()
        self.configure_spectral_plot()
        
        # Color palette for multiple spectra
        colors = plt.cm.tab10(np.linspace(0, 1, len(self.cached_spectral_data)))
        
        # Plot each cached spectrum
        for spectrum_data in self.cached_spectral_data:
            self.spectral_axes.plot(spectrum_data['wavelengths'], 
                                  spectrum_data['reflectance'],
                                  color=colors[spectrum_data['color_index']], 
                                  label=spectrum_data['label'], 
                                  alpha=0.8, 
                                  linewidth=1.5)
        
        # Update plot with dataset title
        dataset_title = self.current_selection.get('ecosis', {}).get('package_title', 'Unknown')
        self.spectral_axes.set_title(f"Spectral Data: {dataset_title}")
        
        # Set reasonable axis limits
        self.spectral_axes.set_xlim(300, 2500)
        self.spectral_axes.set_ylim(0, 1)
        
        # Configure legend
        if self.cached_spectral_data:
            legend = self.spectral_axes.legend(loc='upper right', 
                                             framealpha=0.9, 
                                             fancybox=True, 
                                             shadow=True)
            # Adjust legend text color for dark mode
            if wx.SystemSettings.GetAppearance().IsDark():
                for text in legend.get_texts():
                    text.set_color('white')
        
        # Apply tight layout and draw
        self.spectral_figure.tight_layout()
        self.spectral_canvas.draw()
    
    def create_spectrum_label(self, spectrum, spectrum_num):
        """Create a meaningful label for spectrum legend - WITH DEBUG"""
        print(f"DEBUG: create_spectrum_label - Creating label for spectrum {spectrum_num}")
        print(f"DEBUG: create_spectrum_label - Available spectrum keys: {list(spectrum.keys())[:10]}")  # Show first 10 keys
        
        # Priority order for creating informative labels
        label_parts = []
        
        # 1. Try scientific name
        scientific_name = spectrum.get('Scientific Name')
        if scientific_name:
            if isinstance(scientific_name, list) and scientific_name:
                label_parts.append(str(scientific_name[0]))
            elif isinstance(scientific_name, str):
                label_parts.append(scientific_name)
            print(f"DEBUG: create_spectrum_label - Found scientific name: {scientific_name}")
        
        # 2. Try common name if no scientific name
        if not label_parts:
            common_name = spectrum.get('Common Name')
            if common_name:
                if isinstance(common_name, list) and common_name:
                    label_parts.append(str(common_name[0]))
                elif isinstance(common_name, str):
                    label_parts.append(common_name)
                print(f"DEBUG: create_spectrum_label - Found common name: {common_name}")
        
        # 3. Try sample ID or specimen ID
        if not label_parts:
            for field in ['Sample ID', 'Specimen ID', 'ID', 'Sample_ID', 'Unique_ID']:
                sample_id = spectrum.get(field)
                if sample_id:
                    if isinstance(sample_id, list) and sample_id:
                        label_parts.append(f"ID: {sample_id[0]}")
                    elif isinstance(sample_id, str):
                        label_parts.append(f"ID: {sample_id}")
                    print(f"DEBUG: create_spectrum_label - Found {field}: {sample_id}")
                    break
        
        # 4. Try plot/site information
        if not label_parts:
            for field in ['Plot', 'Site', 'Location', 'Target_Name']:
                location = spectrum.get(field)
                if location:
                    if isinstance(location, list) and location:
                        label_parts.append(f"{field}: {location[0]}")
                    elif isinstance(location, str):
                        label_parts.append(f"{field}: {location}")
                    print(f"DEBUG: create_spectrum_label - Found {field}: {location}")
                    break
        
        # 5. Try measurement date
        if len(label_parts) < 2:
            for field in ['Date', 'Measurement Date', 'Collection Date', 'Measurement_Year']:
                date = spectrum.get(field)
                if date:
                    if isinstance(date, list) and date:
                        label_parts.append(str(date[0]))
                    elif isinstance(date, str):
                        label_parts.append(date)
                    print(f"DEBUG: create_spectrum_label - Found {field}: {date}")
                    break
        
        # 6. Fallback to generic spectrum number
        if not label_parts:
            final_label = f"Spectrum {spectrum_num}"
            print(f"DEBUG: create_spectrum_label - Using fallback label: {final_label}")
            return final_label
        
        # Combine parts (limit to 2 parts for readability)
        label = " - ".join(label_parts[:2])
        
        # Add spectrum number if we have other info
        if label_parts:
            final_label = f"S{spectrum_num}: {label}"
        else:
            final_label = f"Spectrum {spectrum_num}"
        
        print(f"DEBUG: create_spectrum_label - Final label: {final_label}")
        return final_label
            
    def on_calculate_indices(self, event):
        """Calculate vegetation indices for current spectral data"""
        if not self.current_selection:
            wx.MessageBox("Please load spectral data first", "No Data", wx.OK | wx.ICON_WARNING)
            return
            
        try:
            # Get spectral statistics to calculate indices
            base_url = self.url_text.GetValue().rstrip('/')
            dataset_id = self.current_selection.get('_id')
            
            stats_url = f"{base_url}/api/spectra/stats/{dataset_id}"
            response = requests.get(stats_url, timeout=30)
            
            if response.status_code == 200:
                stats_data = response.json()
                
                # Calculate common vegetation indices
                indices_results = {}
                
                # Try to calculate NDVI (NIR - Red) / (NIR + Red)
                # Look for wavelengths around 670nm (Red) and 800nm (NIR)
                red_bands = [key for key in stats_data.keys() if self.is_near_wavelength(key, 670, 20)]
                nir_bands = [key for key in stats_data.keys() if self.is_near_wavelength(key, 800, 50)]
                
                if red_bands and nir_bands:
                    red_key = min(red_bands, key=lambda x: abs(float(x) - 670))
                    nir_key = min(nir_bands, key=lambda x: abs(float(x) - 800))
                    
                    red_avg = float(stats_data[red_key]['avg'])
                    nir_avg = float(stats_data[nir_key]['avg'])
                    
                    ndvi = (nir_avg - red_avg) / (nir_avg + red_avg) if (nir_avg + red_avg) != 0 else 0
                    indices_results['NDVI'] = f"{ndvi:.4f} (Red: {red_key}nm, NIR: {nir_key}nm)"
                
                # Calculate other indices if possible
                green_bands = [key for key in stats_data.keys() if self.is_near_wavelength(key, 550, 30)]
                if green_bands and red_bands and nir_bands:
                    green_key = min(green_bands, key=lambda x: abs(float(x) - 550))
                    green_avg = float(stats_data[green_key]['avg'])
                    
                    # Simple Ratio (SR)
                    sr = nir_avg / red_avg if red_avg != 0 else 0
                    indices_results['Simple Ratio (SR)'] = f"{sr:.4f}"
                    
                    # Green NDVI
                    gndvi = (nir_avg - green_avg) / (nir_avg + green_avg) if (nir_avg + green_avg) != 0 else 0
                    indices_results['GNDVI'] = f"{gndvi:.4f} (Green: {green_key}nm)"
                
                # Display results
                if indices_results:
                    results_text = "Calculated Vegetation Indices:\n\n"
                    for index_name, value in indices_results.items():
                        results_text += f"{index_name}: {value}\n"
                    
                    results_text += f"\nDataset: {self.current_selection.get('ecosis', {}).get('package_title', 'Unknown')}"
                    results_text += f"\nTotal Spectra: {stats_data.get(list(stats_data.keys())[0], {}).get('count', 0)}"
                    
                    wx.MessageBox(results_text, "Vegetation Indices", wx.OK | wx.ICON_INFORMATION)
                else:
                    wx.MessageBox("Could not calculate indices - required wavelengths not found", "Info", wx.OK | wx.ICON_INFORMATION)
                    
            else:
                wx.MessageBox(f"Could not retrieve spectral statistics: HTTP {response.status_code}", "Error", wx.OK | wx.ICON_ERROR)
                
        except Exception as e:
            wx.MessageBox(f"Error calculating indices: {str(e)}", "Error", wx.OK | wx.ICON_ERROR)
    
    def is_near_wavelength(self, key_str, target_wavelength, tolerance):
        """Check if a wavelength key is near the target wavelength within tolerance"""
        try:
            wavelength = float(key_str)
            return abs(wavelength - target_wavelength) <= tolerance
        except ValueError:
            return False
        
    def on_load_photos(self, event):
        """Load and display photos for selected dataset"""
        if not self.current_selection:
            wx.MessageBox("Please select a dataset first", "No Selection", wx.OK | wx.ICON_WARNING)
            return
            
        # Clear existing photos
        self.photo_sizer.Clear(True)
        
        # Load photos from API or dataset
        try:
            # This would fetch photos from the API
            # For now, show placeholder
            placeholder = wx.StaticText(self.photo_panel, label="Photos not available or not yet implemented")
            self.photo_sizer.Add(placeholder, 0, wx.ALL, 10)
            
        except Exception as e:
            error_text = wx.StaticText(self.photo_panel, label=f"Error loading photos: {str(e)}")
            self.photo_sizer.Add(error_text, 0, wx.ALL, 10)
            
        self.photo_panel.Layout()
        
    def on_add_download(self, event):
        """Add selected dataset to download queue"""
        if not self.current_selection:
            wx.MessageBox("Please select a dataset first", "No Selection", wx.OK | wx.ICON_WARNING)
            return
            
        # Add to download list
        index = self.download_list.GetItemCount()
        dataset_title = self.current_selection.get('ecosis', {}).get('package_title', 'Unknown')
        self.download_list.InsertItem(index, dataset_title)
        self.download_list.SetItem(index, 1, "Queued")
        self.download_list.SetItem(index, 2, "0%")
        self.download_list.SetItem(index, 3, "Unknown")
        
    def on_start_downloads(self, event):
        """Start downloading queued datasets"""
        if self.download_list.GetItemCount() == 0:
            wx.MessageBox("No datasets in download queue", "Empty Queue", wx.OK | wx.ICON_WARNING)
            return
            
        # Start download thread
        download_thread = threading.Thread(target=self.download_datasets)
        download_thread.daemon = True
        download_thread.start()
        
    def download_datasets(self):
        """Download all datasets in queue using EcoSIS export API"""
        download_path = self.download_path.GetValue()
        os.makedirs(download_path, exist_ok=True)
        
        base_url = self.url_text.GetValue().rstrip('/')
        total_items = self.download_list.GetItemCount()
        
        for i in range(total_items):
            dataset_name = self.download_list.GetItemText(i)
            wx.CallAfter(self.download_list.SetItem, i, 1, "Downloading")
            
            try:
                # Find the dataset by name in our current data
                dataset_id = None
                for dataset in self.api_data:
                    if dataset.get('ecosis', {}).get('package_title', '') == dataset_name:
                        dataset_id = dataset.get('_id')
                        break
                
                if not dataset_id:
                    wx.CallAfter(self.download_list.SetItem, i, 1, "Error: ID not found")
                    continue
                
                # Use EcoSIS export API
                export_url = f"{base_url}/api/package/{dataset_id}/export"
                params = {
                    'metadata': 'true',  # Include metadata
                    'filters': '[]'  # No additional filters
                }
                
                wx.CallAfter(self.download_list.SetItem, i, 2, "10%")
                
                response = requests.get(export_url, params=params, timeout=120)
                
                wx.CallAfter(self.download_list.SetItem, i, 2, "50%")
                
                if response.status_code == 200:
                    # Save CSV file
                    filename = f"{dataset_name.replace(' ', '_').replace('/', '_')}.csv"
                    filepath = os.path.join(download_path, filename)
                    
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(response.text)
                    
                    wx.CallAfter(self.download_list.SetItem, i, 2, "100%")
                    wx.CallAfter(self.download_list.SetItem, i, 1, "Complete")
                    
                    # Also download dataset metadata as JSON
                    metadata_filename = f"{dataset_name.replace(' ', '_').replace('/', '_')}_metadata.json"
                    metadata_filepath = os.path.join(download_path, metadata_filename)
                    
                    # Find the dataset in our data
                    dataset_metadata = None
                    for dataset in self.api_data:
                        if dataset.get('ecosis', {}).get('package_title', '') == dataset_name:
                            dataset_metadata = dataset
                            break
                    
                    if dataset_metadata:
                        with open(metadata_filepath, 'w', encoding='utf-8') as f:
                            json.dump(dataset_metadata, f, indent=2)
                    
                else:
                    wx.CallAfter(self.download_list.SetItem, i, 1, f"HTTP Error: {response.status_code}")
                
            except requests.RequestException as e:
                wx.CallAfter(self.download_list.SetItem, i, 1, f"Network Error")
            except Exception as e:
                wx.CallAfter(self.download_list.SetItem, i, 1, f"Error: {str(e)[:20]}")
                
            # Update overall progress
            progress = ((i + 1) * 100) // total_items
            wx.CallAfter(self.download_progress_bar.SetValue, progress)
                
        wx.CallAfter(self.download_progress_bar.SetValue, 100)
        wx.CallAfter(self.SetStatusText, "Downloads complete")
        
    def on_pause_downloads(self, event):
        """Pause current downloads"""
        # Implementation for pausing downloads
        pass
        
    def on_clear_queue(self, event):
        """Clear download queue"""
        self.download_list.DeleteAllItems()
        self.download_progress_bar.SetValue(0)
        
    def on_browse_path(self, event):
        """Browse for download directory"""
        dlg = wx.DirDialog(self, "Choose download directory")
        if dlg.ShowModal() == wx.ID_OK:
            self.download_path.SetValue(dlg.GetPath())
        dlg.Destroy()
        
    def on_export_plot(self, event):
        """Export current spectral plot with high quality settings"""
        if not hasattr(self, 'spectral_figure'):
            wx.MessageBox("No plot to export", "Error", wx.OK | wx.ICON_WARNING)
            return
            
        dlg = wx.FileDialog(self, "Save plot as...", 
                           wildcard="PNG files (*.png)|*.png|PDF files (*.pdf)|*.pdf|SVG files (*.svg)|*.svg", 
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        
        if dlg.ShowModal() == wx.ID_OK:
            filepath = dlg.GetPath()
            try:
                # Ensure tight layout before saving
                self.spectral_figure.tight_layout()
                
                # High quality export settings
                self.spectral_figure.savefig(filepath, 
                                           dpi=300, 
                                           bbox_inches='tight',
                                           facecolor=self.spectral_figure.get_facecolor(),
                                           edgecolor='none',
                                           transparent=False)
                
                wx.MessageBox(f"Plot saved successfully to:\n{filepath}", "Export Complete", wx.OK | wx.ICON_INFORMATION)
                
            except Exception as e:
                wx.MessageBox(f"Error saving plot: {str(e)}", "Export Error", wx.OK | wx.ICON_ERROR)
                
        dlg.Destroy()
        
    def on_batch_download(self, event):
        """Add all filtered datasets to download queue"""
        for dataset in self.filtered_data:
            index = self.download_list.GetItemCount()
            dataset_title = dataset.get('ecosis', {}).get('package_title', 'Unknown')
            self.download_list.InsertItem(index, dataset_title)
            self.download_list.SetItem(index, 1, "Queued")
            self.download_list.SetItem(index, 2, "0%")
            self.download_list.SetItem(index, 3, "Unknown")
            
    def on_api_settings(self, event):
        """Show API settings dialog"""
        dlg = APISettingsDialog(self)
        dlg.ShowModal()
        dlg.Destroy()
        
    def on_refresh(self, event):
        """Refresh data from API"""
        self.load_api_data()
        
    def on_exit(self, event):
        """Exit application"""
        self.save_config()
        if self._mgr:
            self._mgr.UnInit()
        self.Destroy()


class APISettingsDialog(wx.Dialog):
    """Dialog for configuring API settings"""
    
    def __init__(self, parent):
        super().__init__(parent, title="API Settings", size=(400, 300))
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # API endpoints configuration
        endpoints_box = wx.StaticBox(self, label="API Endpoints")
        endpoints_sizer = wx.StaticBoxSizer(endpoints_box, wx.VERTICAL)
        
        self.endpoints_list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.endpoints_list.AppendColumn("Endpoint", width=200)
        self.endpoints_list.AppendColumn("Status", width=100)
        
        # Add default endpoints
        endpoints = [
            ("datasets", "Active"),
            ("spectral", "Active"),
            ("hyperspectral", "Active"),
            ("multispectral", "Active")
        ]
        
        for i, (endpoint, status) in enumerate(endpoints):
            self.endpoints_list.InsertItem(i, endpoint)
            self.endpoints_list.SetItem(i, 1, status)
            
        endpoints_sizer.Add(self.endpoints_list, 1, wx.EXPAND | wx.ALL, 5)
        sizer.Add(endpoints_sizer, 1, wx.EXPAND | wx.ALL, 10)
        
        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        test_btn = wx.Button(self, label="Test Connection")
        btn_sizer.Add(test_btn, 0, wx.ALL, 5)
        
        ok_btn = wx.Button(self, wx.ID_OK, "OK")
        cancel_btn = wx.Button(self, wx.ID_CANCEL, "Cancel")
        btn_sizer.Add(ok_btn, 0, wx.ALL, 5)
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 5)
        
        sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        
        self.SetSizer(sizer)


class EcosysApp(wx.App):
    """Main application class"""
    
    def OnInit(self):
        frame = EcosysAPICurator()
        frame.Show()
        return True


if __name__ == '__main__':
    app = EcosysApp()
    app.MainLoop()
