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
        document.body.appendChild(anomalyPopup);
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
            const position = evt.originalEvent;
            anomalyPopup.style.left = (position.pageX + 15) + 'px';
            anomalyPopup.style.top = (position.pageY - 10) + 'px';
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
    }
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
