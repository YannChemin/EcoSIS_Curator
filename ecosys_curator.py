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
from urllib.parse import urlparse, urljoin

import psutil
import os
import json
import gc
import threading
import time

class BatchProgressDialog(wx.Dialog):
    """Non-blocking progress dialog for batch processing"""
    
    def __init__(self, parent, total_batches):
        super().__init__(parent, title="Batch Processing Progress", 
                        size=(500, 300), 
                        style=wx.DEFAULT_DIALOG_STYLE | wx.STAY_ON_TOP)
        
        self.total_batches = total_batches
        self.setup_ui()
        self.setup_timer()
        
        # Center on parent
        self.CenterOnParent()
        
    def setup_ui(self):
        """Setup the progress dialog UI"""
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Title
        title = wx.StaticText(self, label="Processing Spectral Data in Batches")
        title_font = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title.SetFont(title_font)
        main_sizer.Add(title, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        # Overall progress
        main_sizer.Add(wx.StaticText(self, label="Overall Progress:"), 0, wx.ALL, 5)
        self.overall_gauge = wx.Gauge(self, range=self.total_batches, size=(400, 25))
        main_sizer.Add(self.overall_gauge, 0, wx.EXPAND | wx.ALL, 5)
        
        # Batch progress
        main_sizer.Add(wx.StaticText(self, label="Current Batch:"), 0, wx.ALL, 5)
        self.batch_gauge = wx.Gauge(self, range=100, size=(400, 20))
        main_sizer.Add(self.batch_gauge, 0, wx.EXPAND | wx.ALL, 5)
        
        # Status text
        self.status_text = wx.StaticText(self, label="Initializing...")
        main_sizer.Add(self.status_text, 0, wx.ALL, 10)
        
        # Statistics panel
        stats_panel = wx.Panel(self)
        stats_sizer = wx.FlexGridSizer(rows=4, cols=2, hgap=10, vgap=5)
        
        stats_sizer.Add(wx.StaticText(stats_panel, label="Batches Completed:"), 0, wx.ALIGN_RIGHT)
        self.batches_label = wx.StaticText(stats_panel, label="0 / 0")
        stats_sizer.Add(self.batches_label, 0)
        
        stats_sizer.Add(wx.StaticText(stats_panel, label="Datasets Processed:"), 0, wx.ALIGN_RIGHT)
        self.datasets_label = wx.StaticText(stats_panel, label="0")
        stats_sizer.Add(self.datasets_label, 0)
        
        stats_sizer.Add(wx.StaticText(stats_panel, label="Spectra Processed:"), 0, wx.ALIGN_RIGHT)
        self.spectra_label = wx.StaticText(stats_panel, label="0")
        stats_sizer.Add(self.spectra_label, 0)
        
        stats_sizer.Add(wx.StaticText(stats_panel, label="Memory Usage:"), 0, wx.ALIGN_RIGHT)
        self.memory_label = wx.StaticText(stats_panel, label="Monitoring...")
        stats_sizer.Add(self.memory_label, 0)
        
        stats_panel.SetSizer(stats_sizer)
        main_sizer.Add(stats_panel, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        # Control buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.minimize_btn = wx.Button(self, label="Minimize to Background")
        self.minimize_btn.Bind(wx.EVT_BUTTON, self.on_minimize)
        button_sizer.Add(self.minimize_btn, 0, wx.ALL, 5)
        
        button_sizer.AddStretchSpacer()
        
        self.cancel_btn = wx.Button(self, label="Stop Processing")
        self.cancel_btn.Bind(wx.EVT_BUTTON, self.on_cancel)
        button_sizer.Add(self.cancel_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        self.SetSizer(main_sizer)
        
        # Track cancellation
        self.cancelled = False
        
    def setup_timer(self):
        """Setup timer for progress updates"""
        self.update_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer_update, self.update_timer)
        self.update_timer.Start(250)  # Update every 250ms
        
    def on_timer_update(self, event):
        """Update progress from parent's batch_progress"""
        parent = self.GetParent()
        if not hasattr(parent, 'batch_progress'):
            return
            
        progress = parent.batch_progress
        
        # Update overall progress
        self.overall_gauge.SetValue(progress['current_batch'] - 1)
        self.batches_label.SetLabel(f"{progress['successful_batches']} / {progress['total_batches']}")
        
        # Update current batch progress (estimate based on file progress)
        if progress['current_batch_files'] > 0:
            batch_percent = int((progress['current_file'] * 100) / progress['current_batch_files'])
            self.batch_gauge.SetValue(batch_percent)
        
        # Update status
        self.status_text.SetLabel(progress['current_status'])
        
        # Update statistics
        self.datasets_label.SetLabel(f"{progress['total_datasets']:,}")
        self.spectra_label.SetLabel(f"{progress['total_spectra']:,}")
        
        # Update memory usage if available
        try:
            memory_percent = psutil.virtual_memory().percent
            current_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            self.memory_label.SetLabel(f"{current_mb:.0f}MB ({memory_percent:.1f}% system)")
        except:
            self.memory_label.SetLabel("Unknown")
        
        # Check if completed
        if progress['completed'] or progress['error']:
            self.update_timer.Stop()
            if progress['completed']:
                self.on_completion()
            else:
                self.on_error(progress['error'])
    
    def on_minimize(self, event):
        """Minimize dialog to background"""
        self.Hide()
        self.GetParent().SetStatusText("Batch processing continues in background (check taskbar)")
        
    def on_cancel(self, event):
        """Request cancellation of batch processing"""
        if wx.MessageBox("Stop the current batch processing?\nProgress will be lost.", 
                        "Confirm Stop", wx.YES_NO | wx.ICON_QUESTION) == wx.YES:
            self.cancelled = True
            parent = self.GetParent()
            if hasattr(parent, 'batch_progress'):
                parent.batch_progress['error'] = "Cancelled by user"
            self.Close()
    
    def on_completion(self):
        """Handle successful completion"""
        self.status_text.SetLabel("Batch processing completed successfully!")
        self.cancel_btn.SetLabel("Close")
        self.minimize_btn.Enable(False)
        
        # Show completion message
        parent = self.GetParent()
        if hasattr(parent, 'batch_progress'):
            progress = parent.batch_progress
            completion_msg = (f"All batches completed!\n\n"
                             f"Processed: {progress['total_datasets']:,} datasets\n"
                             f"Total spectra: {progress['total_spectra']:,} spectra")
            
            wx.MessageBox(completion_msg, "Processing Complete", 
                         wx.OK | wx.ICON_INFORMATION, self)
    
    def on_error(self, error_msg):
        """Handle processing error"""
        self.status_text.SetLabel(f"Error: {error_msg}")
        self.cancel_btn.SetLabel("Close")
        self.minimize_btn.Enable(False)
        
        wx.MessageBox(f"Batch processing failed:\n{error_msg}", 
                     "Processing Error", wx.OK | wx.ICON_ERROR, self)

def start_batch_processing_thread(self, spectra_files, output_dir, files_per_batch):
    """Start batch processing with responsive progress dialog"""
    # Store output directory for later use
    self.last_batch_output_dir = output_dir
    
    # Calculate total batches
    total_batches = (len(spectra_files) + files_per_batch - 1) // files_per_batch
    
    # Create and show progress dialog
    self.progress_dialog = BatchProgressDialog(self, total_batches)
    self.progress_dialog.Show()
    
    # Disable merge controls
    self.set_merge_controls_enabled(False)
    
    # Show initial status
    self.SetStatusText("Starting batch processing...")
    
    # Create and start background thread
    self.batch_thread = threading.Thread(
        target=self.batch_processing_worker,
        args=(spectra_files, output_dir, files_per_batch),
        daemon=True
    )
    self.batch_thread.start()

def batch_processing_worker(self, spectra_files, output_dir, files_per_batch):
    """Background worker with better progress reporting"""
    import gc
    import time
    
    try:
        total_batches = (len(spectra_files) + files_per_batch - 1) // files_per_batch
        
        # Initialize progress tracking
        self.batch_progress = {
            'current_batch': 0,
            'total_batches': total_batches,
            'current_file': 0,
            'current_batch_files': 0,
            'successful_batches': 0,
            'total_datasets': 0,
            'total_spectra': 0,
            'current_status': 'Starting batch processing...',
            'completed': False,
            'error': None
        }
        
        for batch_num in range(total_batches):
            # Check for cancellation
            if hasattr(self, 'progress_dialog') and self.progress_dialog.cancelled:
                self.batch_progress['error'] = "Cancelled by user"
                return
            
            start_idx = batch_num * files_per_batch
            end_idx = min((batch_num + 1) * files_per_batch, len(spectra_files))
            batch_files = spectra_files[start_idx:end_idx]
            
            # Update progress
            self.batch_progress['current_batch'] = batch_num + 1
            self.batch_progress['current_batch_files'] = len(batch_files)
            self.batch_progress['current_file'] = 0
            self.batch_progress['current_status'] = f'Starting batch {batch_num + 1}/{total_batches}...'
            
            # Process single batch
            batch_output = os.path.join(output_dir, f"merged_spectra_batch_{batch_num + 1:03d}.json")
            batch_datasets, batch_spectra = self.process_single_batch_threaded(batch_files, batch_output)
            
            if batch_datasets > 0:
                self.batch_progress['successful_batches'] += 1
                self.batch_progress['total_datasets'] += batch_datasets
                self.batch_progress['total_spectra'] += batch_spectra
                
                print(f"DEBUG: Batch {batch_num + 1} complete: {batch_datasets} datasets, {batch_spectra} spectra")
            
            # Update status
            self.batch_progress['current_status'] = f'Completed batch {batch_num + 1}/{total_batches}'
            
            # Cleanup and brief pause
            gc.collect()
            time.sleep(0.1)
        
        # Mark as completed
        self.batch_progress['completed'] = True
        self.batch_progress['current_status'] = 'All batches completed successfully!'
        
        # Re-enable controls after brief delay
        wx.CallAfter(self.cleanup_after_batch_completion)
        
    except Exception as e:
        self.batch_progress['error'] = str(e)
        self.batch_progress['current_status'] = f'Error: {str(e)}'
        print(f"DEBUG: Batch processing thread error: {str(e)}")
        
        # Re-enable controls on error
        wx.CallAfter(self.cleanup_after_batch_completion)

def cleanup_after_batch_completion(self):
    """Cleanup after batch processing completes or fails"""
    # Re-enable merge controls
    self.set_merge_controls_enabled(True)
    
    # Close progress dialog after a delay if still open
    if hasattr(self, 'progress_dialog') and self.progress_dialog:
        wx.CallLater(3000, self.close_progress_dialog)  # Auto-close after 3 seconds

def close_progress_dialog(self):
    """Close progress dialog if it exists"""
    if hasattr(self, 'progress_dialog') and self.progress_dialog:
        try:
            self.progress_dialog.Close()
            self.progress_dialog = None
        except:
            pass

class MemoryMonitor:
    """Monitor system memory usage and provide warnings before memory exhaustion with OOM protection"""
    
    def __init__(self, memory_threshold_percent=65, critical_threshold_percent=75):
        # Lower thresholds for OOM protection
        self.memory_threshold_percent = memory_threshold_percent
        self.critical_threshold_percent = critical_threshold_percent
        self.peak_memory_mb = 0
        self.initial_memory_mb = self.get_current_memory_mb()
        self.oom_protection_threshold = 85  # Hard limit to prevent OOM killer
        
    def get_current_memory_mb(self):
        """Get current process memory usage in MB"""
        try:
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / (1024 * 1024)
            
            # Track peak memory usage
            if memory_mb > self.peak_memory_mb:
                self.peak_memory_mb = memory_mb
                
            return memory_mb
        except:
            return 0
            
    def get_system_memory_percent(self):
        """Get system memory usage percentage"""
        try:
            return psutil.virtual_memory().percent
        except:
            return 0
    
    def get_available_memory_gb(self):
        """Get available system memory in GB"""
        try:
            return psutil.virtual_memory().available / (1024 * 1024 * 1024)
        except:
            return 0
            
    def should_pause_processing(self):
        """Check if processing should be paused due to memory pressure with OOM protection"""
        system_percent = self.get_system_memory_percent()
        current_memory_mb = self.get_current_memory_mb()
        available_gb = self.get_available_memory_gb()
        
        # Check for OOM killer risk (immediate stop)
        if system_percent > self.oom_protection_threshold:
            print(f"DEBUG: OOM protection triggered - system memory at {system_percent}%")
            return True
        
        # Check if available memory is critically low
        if available_gb < 0.5:  # Less than 500MB available
            print(f"DEBUG: Critical memory shortage - only {available_gb:.2f}GB available")
            return True
        
        # Check process memory growth
        memory_growth_mb = current_memory_mb - self.initial_memory_mb
        
        # More conservative thresholds for agricultural data processing
        return (system_percent > self.critical_threshold_percent or 
                memory_growth_mb > 500 or  # Reduced from 1GB to 500MB
                current_memory_mb > 800)   # Hard process limit
                
    def get_memory_stats(self):
        """Get comprehensive memory statistics including OOM risk assessment"""
        system_percent = self.get_system_memory_percent()
        current_mb = self.get_current_memory_mb()
        available_gb = self.get_available_memory_gb()
        
        # Calculate OOM risk level
        if system_percent > self.oom_protection_threshold or available_gb < 0.3:
            oom_risk = "CRITICAL"
        elif system_percent > self.critical_threshold_percent or available_gb < 0.8:
            oom_risk = "HIGH"
        elif system_percent > self.memory_threshold_percent or available_gb < 1.5:
            oom_risk = "MODERATE"
        else:
            oom_risk = "LOW"
        
        return {
            'current_mb': current_mb,
            'peak_mb': self.peak_memory_mb,
            'system_percent': system_percent,
            'growth_mb': current_mb - self.initial_memory_mb,
            'available_gb': available_gb,
            'oom_risk': oom_risk
        }

class MergeState:
    """Track merge operation state for resume capability"""
    
    def __init__(self, output_filepath):
        self.output_filepath = output_filepath
        self.state_filepath = output_filepath + '.merge_state'
        self.temp_filepath = output_filepath + '.temp'
        
        # State variables
        self.current_file_index = 0
        self.successful_files = 0
        self.total_spectra = 0
        self.completed_files = []
        
    def save_state(self):
        """Save current merge state to file"""
        try:
            state_data = {
                'output_filepath': self.output_filepath,
                'current_file_index': self.current_file_index,
                'successful_files': self.successful_files,
                'total_spectra': self.total_spectra,
                'completed_files': self.completed_files
            }
            
            with open(self.state_filepath, 'w') as f:
                json.dump(state_data, f, indent=2)
                
        except Exception as e:
            print(f"DEBUG: Error saving merge state: {e}")
            
    def load_state(self):
        """Load merge state from file if it exists"""
        try:
            if os.path.exists(self.state_filepath):
                with open(self.state_filepath, 'r') as f:
                    state_data = json.load(f)
                
                self.current_file_index = state_data.get('current_file_index', 0)
                self.successful_files = state_data.get('successful_files', 0)
                self.total_spectra = state_data.get('total_spectra', 0)
                self.completed_files = state_data.get('completed_files', [])
                
                # Check if temp file exists
                return os.path.exists(self.temp_filepath)
                
        except Exception as e:
            print(f"DEBUG: Error loading merge state: {e}")
            
        return False
        
    def cleanup_state(self):
        """Clean up state and temporary files"""
        try:
            if os.path.exists(self.state_filepath):
                os.remove(self.state_filepath)
            if os.path.exists(self.temp_filepath):
                os.remove(self.temp_filepath)
        except Exception as e:
            print(f"DEBUG: Error cleaning up merge state: {e}")

class EcosysAPICurator(wx.Frame):
    def __init__(self):
        super().__init__(None, title="EcoSIS API Data Curator", size=(1400, 900))
        
        # Initialize variables
        self.api_data = []
        self.filtered_data = []
        self.current_selection = None
        self.download_progress = 0
        self.dataset_photos = {}  # Store photos by dataset ID
        
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
        tools_menu.Append(203, "&Merge Local Spectra", "Merge all local spectra JSON files into one")
        tools_menu.Append(204, "&API Settings", "Configure API endpoints")
        
        menubar.Append(file_menu, "&File")
        menubar.Append(view_menu, "&View")
        menubar.Append(tools_menu, "&Tools")
        
        self.SetMenuBar(menubar)
        
        # Bind menu events
        self.Bind(wx.EVT_MENU, self.on_exit, id=wx.ID_EXIT)
        self.Bind(wx.EVT_MENU, self.on_refresh, id=101)
        self.Bind(wx.EVT_MENU, self.on_batch_download, id=201)
        self.Bind(wx.EVT_MENU, self.on_merge_local_spectra, id=203)
        self.Bind(wx.EVT_MENU, self.on_api_settings, id=204)
        
    def create_api_panel(self):
        """Create API connection and search panel with integrated photo display"""
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
        self.connect_btn = wx.Button(self.api_panel, label="Connect & Load All Data")
        self.connect_btn.Bind(wx.EVT_BUTTON, self.on_connect)
        button_sizer.Add(self.connect_btn, 1, wx.EXPAND|wx.ALL, 5)
        
        self.refresh_btn = wx.Button(self.api_panel, label="Refresh")
        self.refresh_btn.Bind(wx.EVT_BUTTON, self.on_refresh)
        button_sizer.Add(self.refresh_btn, 0, wx.ALL, 5)
        
        api_sizer.Add(button_sizer, 0, wx.EXPAND)
        
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
        self.org_choice.Bind(wx.EVT_TEXT_ENTER, self.on_filter_change)
        org_sizer.Add(self.org_choice, 0, wx.ALL, 5)
        search_sizer.Add(org_sizer, 0, wx.EXPAND)
        
        # Date range filter
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
        
        # Data loading progress and info
        progress_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.data_info = wx.StaticText(self.api_panel, label="No data loaded")
        progress_sizer.Add(self.data_info, 1, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        
        self.loading_gauge = wx.Gauge(self.api_panel, range=100, size=(150, -1))
        progress_sizer.Add(self.loading_gauge, 0, wx.ALL, 5)
        
        search_sizer.Add(progress_sizer, 0, wx.EXPAND)
        
        sizer.Add(search_sizer, 1, wx.EXPAND|wx.ALL, 5)
        
        # Photo viewer section (moved from metadata panel)
        photo_box = wx.StaticBox(self.api_panel, label="Dataset Photos")
        photo_sizer = wx.StaticBoxSizer(photo_box, wx.VERTICAL)
        
        # Photo display area with scrollable panel
        self.photo_scroll = wx.ScrolledWindow(self.api_panel)
        self.photo_scroll.SetScrollRate(10, 10)
        self.photo_scroll.SetMinSize((300, 250))
        self.photo_scroll.SetBackgroundColour(wx.Colour(240, 240, 240))
        
        self.photo_panel_sizer = wx.BoxSizer(wx.VERTICAL)
        self.photo_label = wx.StaticText(self.photo_scroll, label="Select a dataset to view photos")
        self.photo_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
        self.photo_panel_sizer.Add(self.photo_label, 0, wx.ALIGN_CENTER|wx.ALL, 10)
        
        self.photo_scroll.SetSizer(self.photo_panel_sizer)
        photo_sizer.Add(self.photo_scroll, 1, wx.EXPAND|wx.ALL, 5)
        
        # Photo controls
        photo_controls = wx.BoxSizer(wx.HORIZONTAL)
        self.refresh_photos_btn = wx.Button(self.api_panel, label="Refresh Photos")
        self.refresh_photos_btn.Bind(wx.EVT_BUTTON, self.on_refresh_photos)
        photo_controls.Add(self.refresh_photos_btn, 0, wx.ALL, 5)
        
        self.open_dataset_btn = wx.Button(self.api_panel, label="Open Dataset Page")
        self.open_dataset_btn.Bind(wx.EVT_BUTTON, self.on_open_dataset_page)
        photo_controls.Add(self.open_dataset_btn, 0, wx.ALL, 5)
        
        photo_sizer.Add(photo_controls, 0, wx.EXPAND|wx.ALL, 5)
        
        sizer.Add(photo_sizer, 1, wx.EXPAND|wx.ALL, 5)
        
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
        if hasattr(self, 'resize_timer') and self.resize_timer.IsRunning():
            self.resize_timer.Stop()
        
        # Start timer for 150ms delay (only redraw after user stops resizing)
        if hasattr(self, 'resize_timer'):
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
                if hasattr(self, 'cached_spectral_data') and self.cached_spectral_data:
                    self.plot_cached_spectral_data()
                else:
                    # Just apply layout for placeholder or empty plot
                    self.spectral_figure.tight_layout()
                    self.spectral_canvas.draw()
        
    def create_metadata_panel(self):
        """Create simplified metadata display panel (no tabs, just text)"""
        self.metadata_panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Simple metadata text display
        self.metadata_text = wx.TextCtrl(self.metadata_panel, style=wx.TE_MULTILINE|wx.TE_READONLY)
        self.metadata_text.SetFont(wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        sizer.Add(self.metadata_text, 1, wx.EXPAND|wx.ALL, 5)
        
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
        
        # Left panel for API controls and photos
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
            
        # Left pane - API controls and photos
        self._mgr.AddPane(self.api_panel, aui.AuiPaneInfo().
                         Name("api_panel").Caption("API, Search & Photos").
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
                         Name("metadata_panel").Caption("Metadata").
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
        self.total_datasets = 0
        self.all_organizations = set()
        self.all_themes = set()
        
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
        
    def extract_photos_from_dataset(self, dataset):
        """Extract photo URLs from dataset metadata"""
        photos = []
        dataset_id = dataset.get('_id', '')
        
        try:
            # Common photo field names to check
            photo_fields = [
                'photo_url', 'photo_urls', 'image_url', 'image_urls', 
                'photos', 'images', 'Photo_URL', 'Image_URL',
                'Photo', 'Image', 'picture', 'pictures'
            ]
            
            # Check dataset level photo fields
            for field in photo_fields:
                if field in dataset:
                    photo_data = dataset[field]
                    if isinstance(photo_data, str) and self.is_valid_image_url(photo_data):
                        photos.append({
                            'url': photo_data,
                            'title': f"Dataset Photo",
                            'source': 'dataset_metadata'
                        })
                    elif isinstance(photo_data, list):
                        for i, photo_url in enumerate(photo_data):
                            if isinstance(photo_url, str) and self.is_valid_image_url(photo_url):
                                photos.append({
                                    'url': photo_url,
                                    'title': f"Dataset Photo {i+1}",
                                    'source': 'dataset_metadata'
                                })
            
            # Check EcoSIS specific metadata
            ecosis_info = dataset.get('ecosis', {})
            for field in photo_fields:
                if field in ecosis_info:
                    photo_data = ecosis_info[field]
                    if isinstance(photo_data, str) and self.is_valid_image_url(photo_data):
                        photos.append({
                            'url': photo_data,
                            'title': f"EcoSIS Photo",
                            'source': 'ecosis_metadata'
                        })
            
            # Store photos for this dataset
            if photos:
                self.dataset_photos[dataset_id] = photos
                print(f"DEBUG: Found {len(photos)} photos for dataset {dataset_id}")
                
        except Exception as e:
            print(f"DEBUG: Error extracting photos from dataset {dataset_id}: {e}")
            
        return photos
        
    def is_valid_image_url(self, url):
        """Check if URL appears to be a valid image URL"""
        if not isinstance(url, str) or not url.strip():
            return False
            
        url = url.strip().lower()
        
        # Check for common image file extensions
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp']
        
        # Basic URL validation
        if not (url.startswith('http://') or url.startswith('https://')):
            return False
            
        # Check if URL ends with image extension
        for ext in image_extensions:
            if url.endswith(ext):
                return True
                
        # Additional checks for image URLs without extensions but with image-related keywords
        image_keywords = ['photo', 'image', 'picture', 'pic', 'img']
        for keyword in image_keywords:
            if keyword in url:
                return True
                
        return False
        
    def download_photos_for_dataset(self, dataset):
        """Download photos for a dataset in background thread"""
        dataset_id = dataset.get('_id', '')
        if dataset_id not in self.dataset_photos:
            return
            
        def download_photos():
            download_path = os.path.join(self.download_path.GetValue(), "photos", dataset_id)
            os.makedirs(download_path, exist_ok=True)
            
            for i, photo_info in enumerate(self.dataset_photos[dataset_id]):
                try:
                    response = requests.get(photo_info['url'], timeout=30)
                    if response.status_code == 200:
                        # Determine file extension from content type or URL
                        content_type = response.headers.get('content-type', '')
                        if 'jpeg' in content_type or 'jpg' in content_type:
                            ext = '.jpg'
                        elif 'png' in content_type:
                            ext = '.png'
                        elif 'gif' in content_type:
                            ext = '.gif'
                        else:
                            # Try to extract from URL
                            parsed_url = urlparse(photo_info['url'])
                            path = parsed_url.path.lower()
                            for img_ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
                                if path.endswith(img_ext):
                                    ext = img_ext
                                    break
                            else:
                                ext = '.jpg'  # Default fallback
                        
                        filename = f"photo_{i+1}{ext}"
                        filepath = os.path.join(download_path, filename)
                        
                        with open(filepath, 'wb') as f:
                            f.write(response.content)
                            
                        # Update photo info with local path
                        photo_info['local_path'] = filepath
                        
                        print(f"DEBUG: Downloaded photo {i+1} for dataset {dataset_id}")
                        
                except Exception as e:
                    print(f"DEBUG: Error downloading photo {i+1} for dataset {dataset_id}: {e}")
        
        # Start download in background thread
        download_thread = threading.Thread(target=download_photos, daemon=True)
        download_thread.start()
        
    def display_photos_for_dataset(self, dataset):
        """Display photos for the selected dataset"""
        if not dataset:
            return
            
        dataset_id = dataset.get('_id', '')
        dataset_title = dataset.get('ecosis', {}).get('package_title', 'Unknown')
        
        # Clear existing photos
        self.photo_panel_sizer.Clear(True)
        
        # Update label
        self.photo_label = wx.StaticText(self.photo_scroll, label=f"Photos for: {dataset_title}")
        self.photo_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.photo_panel_sizer.Add(self.photo_label, 0, wx.ALL, 10)
        
        # Check if we have photos for this dataset
        photos = self.dataset_photos.get(dataset_id, [])
        
        if not photos:
            no_photos_label = wx.StaticText(self.photo_scroll, label="No photos available for this dataset")
            no_photos_label.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
            self.photo_panel_sizer.Add(no_photos_label, 0, wx.ALIGN_CENTER|wx.ALL, 10)
        else:
            # Display photos
            for i, photo_info in enumerate(photos):
                try:
                    # Create a panel for each photo
                    photo_panel = wx.Panel(self.photo_scroll)
                    photo_sizer = wx.BoxSizer(wx.VERTICAL)
                    
                    # Photo title
                    photo_title = wx.StaticText(photo_panel, label=photo_info['title'])
                    photo_title.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
                    photo_sizer.Add(photo_title, 0, wx.ALL, 5)
                    
                    # Check if we have a local copy
                    if 'local_path' in photo_info and os.path.exists(photo_info['local_path']):
                        try:
                            if Image:
                                # Load and resize image
                                img = Image.open(photo_info['local_path'])
                                img.thumbnail((280, 200), Image.Resampling.LANCZOS)
                                
                                # Convert to wx.Image
                                wx_img = wx.Image(img.size[0], img.size[1])
                                wx_img.SetData(img.convert('RGB').tobytes())
                                
                                # Create bitmap and display
                                bitmap = wx.Bitmap(wx_img)
                                img_ctrl = wx.StaticBitmap(photo_panel, bitmap=bitmap)
                                photo_sizer.Add(img_ctrl, 0, wx.ALIGN_CENTER|wx.ALL, 5)
                            
                        except Exception as e:
                            print(f"DEBUG: Error loading local image: {e}")
                            # Fallback to URL link
                            url_link = wx.StaticText(photo_panel, label=f"Local image error, URL: {photo_info['url'][:50]}...")
                            photo_sizer.Add(url_link, 0, wx.ALL, 5)
                    else:
                        # Show URL link
                        url_link = wx.StaticText(photo_panel, label=f"URL: {photo_info['url'][:50]}...")
                        url_link.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_ITALIC, wx.FONTWEIGHT_NORMAL))
                        photo_sizer.Add(url_link, 0, wx.ALL, 5)
                        
                        # Add "Open URL" button
                        open_btn = wx.Button(photo_panel, label="Open in Browser")
                        open_btn.photo_url = photo_info['url']  # Store URL in button
                        open_btn.Bind(wx.EVT_BUTTON, self.on_open_photo_url)
                        photo_sizer.Add(open_btn, 0, wx.ALIGN_CENTER|wx.ALL, 5)
                    
                    photo_panel.SetSizer(photo_sizer)
                    self.photo_panel_sizer.Add(photo_panel, 0, wx.EXPAND|wx.ALL, 5)
                    
                    # Add separator line
                    if i < len(photos) - 1:
                        line = wx.StaticLine(self.photo_scroll, style=wx.LI_HORIZONTAL)
                        self.photo_panel_sizer.Add(line, 0, wx.EXPAND|wx.ALL, 5)
                
                except Exception as e:
                    print(f"DEBUG: Error displaying photo {i+1}: {e}")
        
        # Refresh layout
        self.photo_scroll.SetSizer(self.photo_panel_sizer)
        self.photo_scroll.FitInside()
        self.photo_scroll.Layout()
        
    def on_open_photo_url(self, event):
        """Open photo URL in web browser"""
        btn = event.GetEventObject()
        if hasattr(btn, 'photo_url'):
            import webbrowser
            webbrowser.open(btn.photo_url)
            
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
        # Use threading to avoid blocking UI
        wx.CallAfter(self.load_api_data_threaded)
        
    def load_api_data_threaded(self):
        """Load API data in a separate thread to avoid blocking UI"""
        loading_thread = threading.Thread(target=self.load_api_data)
        loading_thread.daemon = True
        loading_thread.start()
        
    def load_api_data(self):
        """Load all data from EcoSIS API without pagination"""
        try:
            base_url = self.url_text.GetValue().rstrip('/')
            search_text = self.search_text.GetValue()
            filters = self.build_filters()
            
            # Build API URL for package search
            api_url = f"{base_url}/api/package/search"
            
            # Load all datasets in batches
            all_datasets = []
            batch_size = 100  # Load in batches of 100
            start = 0
            
            wx.CallAfter(self.data_info.SetLabel, "Loading datasets...")
            wx.CallAfter(self.loading_gauge.SetValue, 0)
            
            while True:
                # Prepare query parameters for current batch
                params = {
                    'text': search_text,
                    'filters': json.dumps(filters) if filters else '[]',
                    'start': start,
                    'stop': start + batch_size
                }
                
                # Make API request
                response = requests.get(api_url, params=params, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    
                    if not items:
                        break  # No more data
                    
                    # Extract photos from each dataset as we load them
                    for dataset in items:
                        self.extract_photos_from_dataset(dataset)
                    
                    all_datasets.extend(items)
                    start += batch_size
                    
                    # Update progress
                    total = data.get('total', len(all_datasets))
                    progress = min(100, (len(all_datasets) * 100) // total) if total > 0 else 100
                    wx.CallAfter(self.loading_gauge.SetValue, progress)
                    wx.CallAfter(self.data_info.SetLabel, f"Loaded {len(all_datasets)} of {total} datasets")
                    
                    # If we got fewer items than requested, we've reached the end
                    if len(items) < batch_size:
                        break
                        
                else:
                    wx.CallAfter(self.SetStatusText, f"API Error: HTTP {response.status_code}")
                    return
            
            # Update data
            self.api_data = all_datasets
            self.filtered_data = self.api_data.copy()
            self.total_datasets = len(all_datasets)
            
            # Collect organizations and themes
            self.collect_organizations()
            self.collect_themes()
            
            # Download photos for all datasets in background
            wx.CallAfter(self.download_all_photos)
            
            # Update UI
            wx.CallAfter(self.update_data_grid)
            wx.CallAfter(self.update_organization_combobox)
            wx.CallAfter(self.update_theme_combobox)
            wx.CallAfter(self.SetStatusText, f"Loaded {len(self.api_data)} datasets and {len(self.dataset_photos)} with photos")
            wx.CallAfter(self.data_info.SetLabel, f"Loaded {len(self.api_data)} datasets")
            wx.CallAfter(self.loading_gauge.SetValue, 100)
            
        except requests.RequestException as e:
            wx.CallAfter(self.SetStatusText, f"Connection error: {str(e)}")
            wx.CallAfter(self.data_info.SetLabel, "Connection error")
        except Exception as e:
            wx.CallAfter(self.SetStatusText, f"Error: {str(e)}")
            wx.CallAfter(self.data_info.SetLabel, f"Error: {str(e)}")
            
    def download_all_photos(self):
        """Download photos for all datasets that have them"""
        def download_worker():
            for dataset_id, photos in self.dataset_photos.items():
                # Find the dataset
                dataset = None
                for d in self.api_data:
                    if d.get('_id') == dataset_id:
                        dataset = d
                        break
                
                if dataset:
                    self.download_photos_for_dataset(dataset)
        
        # Start background download
        download_thread = threading.Thread(target=download_worker, daemon=True)
        download_thread.start()

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
           
