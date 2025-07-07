// Anomaly Popup on Map Hover Functions
let anomalyPopup;
let lastHoveredFeature = null;
// Add global reference to the map
window.mapPopupInitialized = false;

/**
 * Create content for the anomaly popup
 * @param {Object} properties - Feature properties
 * @returns {string} HTML content for the popup
 */
function createAnomalyPopupContent(properties) {
    // Compose localisation string
    let localisation = [];
    if (properties.Block) localisation.push('Block - ' + properties.Block);
    if (properties.String) localisation.push('String - ' + properties.String);
    if (properties.panel) localisation.push('Module - ' + properties.panel);
    let localisationStr = localisation.join(', ');
    
    // Status
    let status = properties.status ? properties.status.charAt(0).toUpperCase() + properties.status.slice(1) : 'Pending';
    
    // Anomaly Hash Number
    let hash = properties.ID ? `#${properties.ID}` : '';
    
    // Anomaly Type
    let anomalyType = properties.Anomaly || '';
    
    // Severity with legend
    let severity = properties.Severity || 'N/A';
    let severityWithLegend = `${severity} <span class="severity-legend" onclick="window.showSeverityLegend()" title="Click to see severity classification" style="cursor: pointer; color: #0066cc;">ℹ️</span>`;
    
    // Format datetime
    let formattedDateTime = window.formatDateTime ? window.formatDateTime(properties['Date'], properties['Time']) : formatDateTime(properties['Date'], properties['Time']);
    
    // Additional fields
    let moduleMake = properties.make || 'N/A';
    let moduleWatt = properties.Wat || 'N/A';
    let barcodeSerial = properties.barcode || 'N/A';
    let deltaT = properties.Hotspot || 'N/A';
    
    // Image
    let s3BasePath = window.s3BasePath || '';
    let imageName = properties['Image name'] || properties['Image na'] || '';
    let imagePath = imageName ? `${s3BasePath}/zip_images/${imageName}` : '/static/images/data_check.png';

    return `
        <div class="anomaly-popup-content">
            <img src="${imagePath}" alt="Thermal Image" class="anomaly-popup-image" onerror="this.src='/static/images/data_check.png'" />
            <div class="anomaly-popup-title">${hash} (${anomalyType})</div>
            <div class="anomaly-popup-localisation">${localisationStr}</div>
            <div class="anomaly-popup-status">Status - ${status}</div>
            <div class="anomaly-popup-severity">Severity - ${severityWithLegend}</div>
            <div class="anomaly-popup-datetime">Date Time - ${formattedDateTime}</div>
            <hr style="margin: 8px 0; border: none; border-top: 1px solid #e0e0e0;">
            <div class="anomaly-popup-field">ΔT(T2 - T1) - ${deltaT}</div>
            <div class="anomaly-popup-field">Module Make - ${moduleMake}</div>
            <div class="anomaly-popup-field">Module Watt - ${moduleWatt}</div>
            <div class="anomaly-popup-field">Barcode Serial No. - ${barcodeSerial}</div>
        </div>
    `;
}

/**
 * Show anomaly popup on hover
 * @param {Event} evt - OpenLayers event
 */
function showAnomalyPopupOnHover(evt) {
    if (!anomalyPopup) {
        anomalyPopup = document.createElement('div');
        anomalyPopup.className = 'anomaly-popup';
        anomalyPopup.style.display = 'none';
        
        // Append to the map container or body based on fullscreen state
        const mapElement = document.getElementById('map');
        const isFullscreen = document.fullscreenElement === mapElement || 
                            document.webkitFullscreenElement === mapElement ||
                            document.mozFullScreenElement === mapElement ||
                            document.msFullscreenElement === mapElement;
        
        if (isFullscreen) {
            mapElement.appendChild(anomalyPopup);
        } else {
            document.body.appendChild(anomalyPopup);
        }
    }

    const pixel = evt.pixel;
    let foundFeature = false;

    // Access the map from the global window object
    if (!window.map) return;
    
    window.map.forEachFeatureAtPixel(pixel, function(feature) {
        const properties = feature.getProperties();
        if (properties && (properties['Image name'] || properties['name'] || properties.ID)) {
            foundFeature = true;
            if (lastHoveredFeature !== feature) {
                lastHoveredFeature = feature;
                anomalyPopup.innerHTML = createAnomalyPopupContent(properties);
            }
            
            // Position the popup near the mouse pointer
            // Check if map is in fullscreen mode
            const mapElement = document.getElementById('map');
            const isFullscreen = document.fullscreenElement === mapElement || 
                                document.webkitFullscreenElement === mapElement ||
                                document.mozFullScreenElement === mapElement ||
                                document.msFullscreenElement === mapElement;
            
            let position = evt.originalEvent;
            
            // Adjust positioning for fullscreen mode
            if (isFullscreen) {
                // In fullscreen, position relative to the map container
                const mapRect = mapElement.getBoundingClientRect();
                anomalyPopup.style.position = 'absolute';
                anomalyPopup.style.left = (position.clientX - mapRect.left + 15) + 'px';
                anomalyPopup.style.top = (position.clientY - mapRect.top - 10) + 'px';
                anomalyPopup.style.zIndex = '10002';
            } else {
                // Normal mode positioning relative to document
                anomalyPopup.style.position = 'absolute';
                anomalyPopup.style.left = (position.pageX + 15) + 'px';
                anomalyPopup.style.top = (position.pageY - 10) + 'px';
                anomalyPopup.style.zIndex = '10001';
            }
            
            anomalyPopup.style.display = 'block';
            
            return true; // Stop further searching
        }
    }, {
        hitTolerance: 5 // Make it easier to hit small features
    });

    if (!foundFeature) {
        hideAnomalyPopup();
    }
}

/**
 * Hide the anomaly popup
 */
function hideAnomalyPopup() {
    if (anomalyPopup) {
        anomalyPopup.style.display = 'none';
        lastHoveredFeature = null;
        
        // Remove popup from its current parent and reset for next use
        if (anomalyPopup.parentNode) {
            anomalyPopup.parentNode.removeChild(anomalyPopup);
        }
        anomalyPopup = null; // Reset so it gets recreated with proper parent
    }
}

/**
 * Handle fullscreen change events to ensure popup works correctly
 */
function handleFullscreenChange() {
    // If popup exists, hide it when fullscreen state changes
    if (anomalyPopup) {
        hideAnomalyPopup();
    }
}

/**
 * Format datetime to DD-MM-YYYY, HH:MM:SS format
 * @param {string} dateStr - Date string
 * @param {string} timeStr - Time string
 * @returns {string} Formatted datetime
 */
function formatDateTime(dateStr, timeStr) {
    try {
        // Clean up the date and time strings
        let cleanDate = dateStr ? dateStr.trim() : '';
        let cleanTime = timeStr ? timeStr.trim() : '';
        
        // Remove any trailing .000Z or similar
        cleanTime = cleanTime.replace(/\.\d{3}Z?$/, '');
        
        // Parse the date (assuming it's in YYYY-MM-DD format)
        let dateParts = cleanDate.split('-');
        if (dateParts.length === 3) {
            // Convert to DD-MM-YYYY format
            let formattedDate = `${dateParts[2]}-${dateParts[1]}-${dateParts[0]}`;
            return `${formattedDate}, ${cleanTime}`;
        }
        
        // If parsing fails, return original
        return `${cleanDate}, ${cleanTime}`;
    } catch (error) {
        console.error('Error formatting datetime:', error);
        return `${dateStr}, ${timeStr}`;
    }
}

/**
 * Show severity legend popup
 */
function showSeverityLegend() {
    const legendContent = `
        <div style="font-size: 14px; line-height: 1.6;">
            <h4 style="margin: 0 0 10px 0; color: #333;">Severity Classification (ΔT)</h4>
            <div style="margin-bottom: 8px;">
                <span style="color: #dc3545; font-weight: bold;">🔴 High:</span> ΔT > 20°C
            </div>
            <div style="margin-bottom: 8px;">
                <span style="color: #fd7e14; font-weight: bold;">🟠 Medium:</span> 10°C < ΔT ≤ 20°C
            </div>
            <div style="margin-bottom: 8px;">
                <span style="color: #28a745; font-weight: bold;">🟢 Low:</span> ΔT ≤ 10°C
            </div>
            <div style="font-size: 12px; color: #666; margin-top: 10px;">
                ΔT = Temperature difference between hotspot and ambient
            </div>
        </div>
    `;
    
    // Create a modal-like popup
    const overlay = document.createElement('div');
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        z-index: 10000;
        display: flex;
        justify-content: center;
        align-items: center;
    `;
    
    const popup = document.createElement('div');
    popup.style.cssText = `
        background: white;
        padding: 20px;
        border-radius: 8px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
        max-width: 350px;
        position: relative;
    `;
    
    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '×';
    closeBtn.style.cssText = `
        position: absolute;
        top: 10px;
        right: 15px;
        background: none;
        border: none;
        font-size: 20px;
        cursor: pointer;
        color: #666;
    `;
    
    closeBtn.onclick = () => overlay.remove();
    overlay.onclick = (e) => {
        if (e.target === overlay) overlay.remove();
    };
    
    popup.innerHTML = legendContent;
    popup.appendChild(closeBtn);
    overlay.appendChild(popup);
    document.body.appendChild(overlay);
}

// Initialize map hover functionality
function initializeMapHoverPopup() {
    console.log("Attempting to initialize map hover popup...");
    
    // Store s3BasePath from template in a global variable
    window.s3BasePath = document.getElementById('s3BasePathContainer')?.dataset?.path || '';
    
    // Make sure the map exists in the global scope before adding listeners
    if (!window.map) {
        console.log('Map not found, retrying in 1000ms...');
        setTimeout(initializeMapHoverPopup, 1000);
        return;
    }
    
    if (window.mapPopupInitialized) {
        console.log('Map popup already initialized, skipping...');
        return; // Prevent duplicate initialization
    }
    
    console.log('Map found! Initializing map hover popup...');
    window.mapPopupInitialized = true;
    
    try {
        // Add pointermove listener to show popup
        window.map.on('pointermove', function(evt) {
            if (evt.dragging) {
                hideAnomalyPopup();
                return;
            }
            showAnomalyPopupOnHover(evt);
        });

        // Add pointerleave listener to hide popup when mouse leaves the map
        const viewport = window.map.getViewport();
        if (viewport) {
            viewport.addEventListener('mouseleave', hideAnomalyPopup);
            console.log('Added mouseleave event listener to map viewport');
        } else {
            console.error('Could not get map viewport');
        }
        
        // Add fullscreen change event listeners to handle popup repositioning
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('mozfullscreenchange', handleFullscreenChange);
        document.addEventListener('MSFullscreenChange', handleFullscreenChange);
        
        console.log('Map hover popup initialization complete!');
    } catch (error) {
        console.error('Error initializing map hover popup:', error);
    }
}

// Make these functions globally accessible
window.toggleSidebar = function() {
    const sidebar = document.querySelector('.sidebar');
    const mainContent = document.querySelector('.main-content');
    const header = document.querySelector('.header');
    const toggleBtn = document.querySelector('.toggle-sidebar svg');

    console.log("Toggle sidebar called", {sidebar, mainContent, toggleBtn});

    if (sidebar && mainContent && toggleBtn) {
        sidebar.classList.toggle('collapsed');
        mainContent.classList.toggle('expanded');
        
        // Update header position when sidebar is collapsed/expanded
        if (sidebar.classList.contains('collapsed')) {
            if (header) {
                header.style.left = '60px';
            }
        } else {
            if (header) {
                header.style.left = '150px';
            }
        }

        // Rotate the arrow icon
        if (sidebar.classList.contains('collapsed')) {
            toggleBtn.style.transform = 'rotate(180deg)';
        } else {
            toggleBtn.style.transform = 'rotate(0deg)';
        }
    }
};

// Make formatDateTime and showSeverityLegend globally accessible
window.formatDateTime = formatDateTime;
window.showSeverityLegend = showSeverityLegend;

window.openOverview = function() {
    console.log("openOverview called");
    const plantId = document.querySelector('[data-plant-id]')?.dataset?.plantId;
    console.log("Plant ID:", plantId);
    if (plantId) {
        window.location.href = '/plant/' + plantId + '/overview';
    }
};

window.openSiteDetails = function() {
    console.log("openSiteDetails called");
    const plantId = document.querySelector('[data-plant-id]')?.dataset?.plantId;
    console.log("Plant ID:", plantId);
    if (plantId) {
        window.location.href = '/plant/' + plantId + '/site-details';
    }
};

window.openAnomaliesMap = function() {
    console.log("openAnomaliesMap called");
    const plantId = document.querySelector('[data-plant-id]')?.dataset?.plantId;
    console.log("Plant ID:", plantId);
    if (plantId) {
        // Try to get the first audit for this plant and redirect to its anomalies
        fetch(`/api/plants/${plantId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.plant.audits && data.plant.audits.length > 0) {
                    // Redirect to the first audit's detail page
                    window.location.href = '/audit/' + data.plant.audits[0];
                } else {
                    // Fallback to plant detail page
                    window.location.href = '/plant/' + plantId;
                }
            })
            .catch(error => {
                console.error('Error fetching plant data:', error);
                // Fallback to plant detail page
                window.location.href = '/plant/' + plantId;
            });
    }
};

// Call this function when the document is loaded
document.addEventListener('DOMContentLoaded', function() {
    console.log("Document ready, checking for map...");
    
    // Add global functions to window for direct access from HTML
    if (typeof window.toggleSidebar === 'function') {
        console.log("toggleSidebar is defined globally");
    } else {
        console.error("toggleSidebar is NOT defined globally");
    }
    
    // The map needs to be initialized first, so we'll wait a bit
    setTimeout(function() {
        console.log("Delayed initialization check - Map exists:", !!window.map);
        initializeMapHoverPopup();
    }, 2000);
});