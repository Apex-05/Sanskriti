document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.alert.auto-dismiss').forEach((alertElement) => {
        setTimeout(() => {
            if (window.bootstrap && bootstrap.Alert) {
                bootstrap.Alert.getOrCreateInstance(alertElement).close();
            } else {
                alertElement.classList.remove('show');
                alertElement.remove();
            }
        }, 3000);
    });

    const nav = document.querySelector('.custom-nav');

    if (nav) {
        const updateNav = () => {
            if (window.scrollY > 20) {
                nav.classList.add('nav-scrolled');
            } else {
                nav.classList.remove('nav-scrolled');
            }
        };

        updateNav();
        window.addEventListener('scroll', updateNav, { passive: true });
    }

    const navmenu = document.getElementById('navmenu');
    if (navmenu && window.bootstrap) {
        const collapse = bootstrap.Collapse.getOrCreateInstance(navmenu, { toggle: false });
        document.querySelectorAll('.nav-collapse-link').forEach((link) => {
            link.addEventListener('click', () => {
                if (window.innerWidth < 1200 && navmenu.classList.contains('show')) {
                    collapse.hide();
                }
            });
        });
    }

    const addResilientTileLayer = (mapInstance, providers = []) => {
        if (!mapInstance || typeof L === 'undefined') {
            return null;
        }

        const normalizedProviders = providers.length
            ? providers
            : [
                {
                    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                    options: {
                        maxZoom: 19,
                        subdomains: 'abcd',
                        attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
                    }
                },
                {
                    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
                    options: {
                        maxZoom: 19,
                        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'
                    }
                },
                {
                    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
                    options: {
                        maxZoom: 19,
                        attribution: 'Tiles &copy; Esri'
                    }
                }
            ];

        let providerIndex = 0;
        let activeLayer = null;

        const activateProvider = () => {
            if (activeLayer) {
                mapInstance.removeLayer(activeLayer);
            }

            const provider = normalizedProviders[providerIndex];
            activeLayer = L.tileLayer(provider.url, {
                noWrap: true,
                ...provider.options
            }).addTo(mapInstance);

            let tileErrors = 0;
            activeLayer.on('tileerror', () => {
                tileErrors += 1;
                if (tileErrors >= 3 && providerIndex < normalizedProviders.length - 1) {
                    providerIndex += 1;
                    activateProvider();
                }
            });
        };

        activateProvider();
        return activeLayer;
    };

    const initMapPreview = (mapId, popupMessage, options = {}) => {
        const mapContainer = document.getElementById(mapId);
        if (!mapContainer || typeof L === 'undefined') {
            return null;
        }

        const mapInstance = L.map(mapId, {
            zoomControl: true,
            scrollWheelZoom: false,
            minZoom: options.minZoom ?? 3,
            maxZoom: options.maxZoom ?? 19,
            maxBounds: options.maxBounds ?? null,
            maxBoundsViscosity: options.maxBounds ? 1.0 : 0
        });

        if (options.fitBounds) {
            mapInstance.fitBounds(options.fitBounds, {
                padding: options.fitPadding || [20, 20]
            });
        } else {
            mapInstance.setView([22.5937, 78.9629], 5);
        }

        addResilientTileLayer(mapInstance);

        if (popupMessage) {
            L.marker([22.5937, 78.9629])
                .addTo(mapInstance)
                .bindPopup(popupMessage)
                .openPopup();
        }

        setTimeout(() => {
            mapInstance.invalidateSize();
        }, 180);

        return mapInstance;
    };

    initMapPreview('indiaMap', 'Community cultural uploads will appear here.');

    const addNeighborHighlights = (mapInstance) => {
        if (!mapInstance || typeof L === 'undefined') {
            return;
        }

        const neighborLayer = L.layerGroup().addTo(mapInstance);
        const indiaCenter = [22.5937, 78.9629];
        const neighbors = [
            { name: 'Pakistan', lat: 33.6844, lng: 73.0479, caption: 'West neighbour' },
            { name: 'Nepal', lat: 27.7172, lng: 85.3240, caption: 'Himalayan neighbour' },
            { name: 'Bhutan', lat: 27.4728, lng: 89.6390, caption: 'Eastern Himalayas' },
            { name: 'Bangladesh', lat: 23.8103, lng: 90.4125, caption: 'Bay-side neighbour' },
            { name: 'Myanmar', lat: 19.7633, lng: 96.0785, caption: 'Eastern neighbour' },
            { name: 'Sri Lanka', lat: 6.9271, lng: 79.8612, caption: 'Southern island neighbour' }
        ];

        neighbors.forEach((neighbor) => {
            L.polyline([indiaCenter, [neighbor.lat, neighbor.lng]], {
                color: '#E09F3E',
                weight: 1.5,
                opacity: 0.55,
                dashArray: '4 5'
            }).addTo(neighborLayer);

            L.circleMarker([neighbor.lat, neighbor.lng], {
                radius: 6,
                color: '#7A1E1E',
                weight: 2,
                fillColor: '#FF9933',
                fillOpacity: 0.92
            })
                .addTo(neighborLayer)
                .bindPopup(`<strong>${neighbor.name}</strong><br><small>${neighbor.caption}</small>`);
        });
    };

    let homeMap = null;
    if (typeof L !== 'undefined') {
        const homeMapBounds = L.latLngBounds(
            [5.0, 60.0],
            [38.8, 98.5]
        );

        homeMap = initMapPreview('homeMap', null, {
            minZoom: 4,
            maxZoom: 8,
            maxBounds: homeMapBounds,
            fitBounds: homeMapBounds,
            fitPadding: [16, 16]
        });

        addNeighborHighlights(homeMap);
    }
    const mapSection = document.getElementById('map');
    const culturalGrid = document.getElementById('culturalGrid');
    const placesDatasetMeta = document.getElementById('placesDatasetMeta');

    let activePlaceMarker = null;

    const buildPlaceCards = () => {
        if (!culturalGrid || !Array.isArray(window.culturalPlaces)) {
            return;
        }

        if (placesDatasetMeta) {
            placesDatasetMeta.textContent = `${window.culturalPlaces.length} places from your cultural dataset.`;
        }

        const cardsFragment = document.createDocumentFragment();

        window.culturalPlaces.forEach((place) => {
            const placeRegion = place.state || place.region || place.location || '';
            const placeDescription = place.description || '';

            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'grid-card grid-scroll-link reveal-card';
            button.setAttribute('aria-label', placeRegion ? `${place.name}, ${placeRegion}` : place.name);
            if (placeDescription) {
                button.setAttribute('title', placeDescription);
            }

            const image = document.createElement('img');
            image.className = 'lazy-grid-image';
            image.src = place.image;
            image.alt = placeRegion ? `${place.name}, ${placeRegion}` : place.name;

            const overlay = document.createElement('span');
            overlay.className = 'grid-overlay';
            overlay.innerHTML = placeRegion
                ? `<strong>${place.name}</strong> - ${placeRegion}`
                : `<strong>${place.name}</strong>`;

            button.appendChild(image);
            button.appendChild(overlay);

            button.addEventListener('click', () => {
                if (mapSection) {
                    mapSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }

                if (!homeMap) {
                    return;
                }

                // Wait for scroll animation
                setTimeout(() => {
                    // Force map to recalculate its size
                    homeMap.invalidateSize({ animate: false });
                    
                    // Remove existing marker if any
                    if (activePlaceMarker) {
                        homeMap.removeLayer(activePlaceMarker);
                    }

                    const mapWidth = homeMap.getSize().x;
                    const mapHeight = homeMap.getSize().y;
                    
                    // Use conservative zoom to ensure popup fits
                    let targetZoom = 5;
                    if (mapWidth >= 760 && mapHeight >= 600) {
                        targetZoom = 6;
                    } else if (mapWidth >= 520 && mapHeight >= 500) {
                        targetZoom = 5.5;
                    }

                    // Prepare popup content
                    const descriptionParts = (place.description || '').split('—');
                    const popupState = (descriptionParts[0] || placeRegion || '').trim();
                    const popupDescription = (descriptionParts[1] || place.description || '').trim();
                    const popupHTML = `
<div class="map-popup">
    <img src="${place.image}" class="popup-image" alt="${place.name}">

    <div class="popup-content">
        <h5 class="popup-title">${place.name}</h5>
        <div class="popup-state">${popupState}</div>
        <p class="popup-desc">${popupDescription}</p>
    </div>
</div>
`;

                    // Use setView for immediate positioning, then create marker
                    homeMap.setView([place.lat, place.lng], targetZoom, {
                        animate: true,
                        duration: 1.0
                    });

                    // Add marker after a short delay
                    setTimeout(() => {
                        activePlaceMarker = L.marker([place.lat, place.lng]).addTo(homeMap);
                        
                        // Bind and open popup
                        activePlaceMarker.bindPopup(popupHTML, {
                            maxWidth: 320,
                            minWidth: 280,
                            autoPan: true,
                            keepInView: true,
                            autoPanPaddingTopLeft: [20, 20],
                            autoPanPaddingBottomRight: [20, 300],
                            autoClose: false,
                            closeOnClick: false
                        }).openPopup();
                    }, 1100);
                }, 500);
            });

            cardsFragment.appendChild(button);
        });

        culturalGrid.innerHTML = '';
        culturalGrid.appendChild(cardsFragment);
    };

    buildPlaceCards();

    const uploadMapModal = document.getElementById('uploadMapModal');
    const uploadMapEl = document.getElementById('uploadMap');
    const coordinatesLabel = document.getElementById('selectedCoordinates');
    const latitudeInput = document.getElementById('latitude');
    const longitudeInput = document.getElementById('longitude');
    const manualLatitudeInput = document.getElementById('manualLatitude');
    const manualLongitudeInput = document.getElementById('manualLongitude');
    const applyManualCoordinatesBtn = document.getElementById('applyManualCoordinates');
    const uploadMapSearchInput = document.getElementById('uploadMapSearchInput');
    const uploadMapSearchBtn = document.getElementById('uploadMapSearchBtn');
    const uploadMapSearchStatus = document.getElementById('uploadMapSearchStatus');
    const locationNameInput = document.getElementById('locationName');
    const stateUtInput = document.getElementById('stateUt');

    let uploadMap;
    let uploadMarker;

    const isValidCoordinatePair = (lat, lng) => (
        Number.isFinite(lat)
        && Number.isFinite(lng)
        && lat >= -90
        && lat <= 90
        && lng >= -180
        && lng <= 180
    );

    const showCoordinateError = (message) => {
        if (!coordinatesLabel) {
            return;
        }

        coordinatesLabel.classList.remove('text-muted');
        coordinatesLabel.classList.add('text-danger');
        coordinatesLabel.textContent = message;
    };

    const updateCoordinatesLabel = (lat, lng) => {
        if (!coordinatesLabel) {
            return;
        }

        coordinatesLabel.classList.remove('text-danger');
        coordinatesLabel.classList.add('text-muted');
        coordinatesLabel.textContent = `Lat: ${lat.toFixed(6)}, Lng: ${lng.toFixed(6)}`;
    };

    const updateSearchStatus = (message, isError = false) => {
        if (!uploadMapSearchStatus) {
            return;
        }

        uploadMapSearchStatus.textContent = message;
        uploadMapSearchStatus.classList.toggle('text-danger', isError);
        uploadMapSearchStatus.classList.toggle('text-muted', !isError);
    };

    const syncResolvedLocationFields = (displayName, addressData = {}, forceUpdate = false) => {
        const firstSegment = String(displayName || '').split(',')[0].trim();
        if (locationNameInput && firstSegment && (forceUpdate || !locationNameInput.value.trim())) {
            locationNameInput.value = firstSegment;
        }

        if (!stateUtInput) {
            return;
        }

        const candidateState = (
            addressData.state
            || addressData.state_district
            || addressData.region
            || ''
        ).trim();

        if (!candidateState || (!forceUpdate && stateUtInput.value)) {
            return;
        }

        const normalizedCandidate = candidateState.toLowerCase();
        const matchingOption = Array.from(stateUtInput.options).find((option) => {
            if (!option.value) {
                return false;
            }
            const normalizedOption = option.value.toLowerCase();
            return (
                normalizedOption === normalizedCandidate
                || normalizedCandidate.includes(normalizedOption)
                || normalizedOption.includes(normalizedCandidate)
            );
        });

        if (matchingOption) {
            stateUtInput.value = matchingOption.value;
        }
    };

    const syncManualCoordinateInputs = (lat, lng) => {
        if (manualLatitudeInput) {
            manualLatitudeInput.value = lat.toFixed(6);
        }
        if (manualLongitudeInput) {
            manualLongitudeInput.value = lng.toFixed(6);
        }
    };

    const reverseGeocodeAndFillLocation = async (lat, lng, forceUpdate = false) => {
        try {
            const response = await window.fetch(`/api/reverse-geocode/?lat=${lat}&lng=${lng}`, {
                credentials: 'same-origin',
                headers: {
                    Accept: 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            if (!response.ok) {
                console.warn('Reverse geocoding failed');
                return;
            }

            const data = await response.json();
            
            if (data.display_name) {
                syncResolvedLocationFields(data.display_name, data.address || {}, forceUpdate);
                updateSearchStatus('Location details auto-filled. Click map to fine-tune.', false);
            }
        } catch (error) {
            console.warn('Reverse geocoding error:', error);
        }
    };

    const setUploadMarker = (lat, lng, shouldCenterMap, label, openPopup = false) => {
        if (!uploadMap) {
            return;
        }

        if (uploadMarker) {
            uploadMarker.setLatLng([lat, lng]);
            if (!uploadMap.hasLayer(uploadMarker)) {
                uploadMarker.addTo(uploadMap);
            }
        } else {
            uploadMarker = L.marker([lat, lng]).addTo(uploadMap);
        }

        if (label) {
            uploadMarker.bindPopup(label);
        }

        if (shouldCenterMap) {
            uploadMap.setView([lat, lng], 14, { animate: true, duration: 0.8 });
        }

        if (label && openPopup) {
            uploadMarker.openPopup();
        }
    };

    const setUploadCoordinates = (lat, lng, options = {}) => {
        const {
            updateMap = true,
            centerMap = false,
            label = '',
            openPopup = false,
        } = options;

        if (!isValidCoordinatePair(lat, lng)) {
            showCoordinateError('Please enter valid coordinates (latitude -90 to 90, longitude -180 to 180).');
            return;
        }

        if (latitudeInput) {
            latitudeInput.value = lat.toFixed(6);
        }
        if (longitudeInput) {
            longitudeInput.value = lng.toFixed(6);
        }

        syncManualCoordinateInputs(lat, lng);
        updateCoordinatesLabel(lat, lng);

        if (updateMap && uploadMap) {
            setUploadMarker(lat, lng, centerMap, label, openPopup);
        }
    };

    const initializeUploadMap = () => {
        if (uploadMap || !uploadMapEl || typeof L === 'undefined') {
            return;
        }

        uploadMap = L.map('uploadMap', {
            scrollWheelZoom: false
        }).setView([22.5937, 78.9629], 5);

        addResilientTileLayer(uploadMap);

        uploadMap.on('click', (event) => {
            const { lat, lng } = event.latlng;
            setUploadCoordinates(lat, lng, { updateMap: true, centerMap: false });
            
            // Trigger reverse geocoding to auto-fill location name and state
            reverseGeocodeAndFillLocation(lat, lng, true);
            
            updateSearchStatus('Pin updated. Fetching location details...', false);
        });

        const existingLat = latitudeInput ? Number.parseFloat(latitudeInput.value) : Number.NaN;
        const existingLng = longitudeInput ? Number.parseFloat(longitudeInput.value) : Number.NaN;
        if (isValidCoordinatePair(existingLat, existingLng)) {
            setUploadMarker(existingLat, existingLng, true, 'Selected location');
        }
    };

    const searchUploadLocation = async () => {
        if (!uploadMapSearchInput) {
            return;
        }

        const query = uploadMapSearchInput.value.trim();
        if (!query) {
            updateSearchStatus('Enter a location name to search.', true);
            return;
        }

        initializeUploadMap();

        if (!uploadMap) {
            updateSearchStatus('Map is not ready yet. Try again.', true);
            return;
        }

        if (uploadMapSearchBtn) {
            uploadMapSearchBtn.disabled = true;
        }

        updateSearchStatus('Searching location...', false);

        try {
            const proxyUrl = `/api/geocode/?q=${encodeURIComponent(query)}`;

            const response = await window.fetch(proxyUrl, {
                credentials: 'same-origin',
                headers: {
                    Accept: 'application/json',
                    'X-CSRFToken': getCsrfToken(),
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            if (!response.ok) {
                throw new Error('Search request failed.');
            }

            const data = await response.json();
            const results = data.results || [];
            if (!Array.isArray(results) || !results.length) {
                updateSearchStatus('No location found. Try a different search term.', true);
                return;
            }

            const firstMatch = results[0];
            const lat = Number.parseFloat(firstMatch.lat);
            const lng = Number.parseFloat(firstMatch.lon);

            if (!isValidCoordinatePair(lat, lng)) {
                updateSearchStatus('Found location had invalid coordinates.', true);
                return;
            }

            setUploadCoordinates(lat, lng, {
                updateMap: true,
                centerMap: true,
                label: firstMatch.display_name || query,
                openPopup: true,
            });

            syncResolvedLocationFields(firstMatch.display_name || query, firstMatch.address || {});

            updateSearchStatus('Location found and pinned automatically. Click map to fine-tune.', false);
        } catch (error) {
            updateSearchStatus('Location search failed. Please try again.', true);
        } finally {
            if (uploadMapSearchBtn) {
                uploadMapSearchBtn.disabled = false;
            }
        }
    };

    if (uploadMapModal && uploadMapEl && typeof L !== 'undefined') {
        uploadMapModal.addEventListener('shown.bs.modal', () => {
            initializeUploadMap();

            setTimeout(() => {
                uploadMap.invalidateSize();
            }, 150);
        });
    }

    if (uploadMapSearchBtn) {
        uploadMapSearchBtn.addEventListener('click', () => {
            void searchUploadLocation();
        });
    }

    if (uploadMapSearchInput) {
        uploadMapSearchInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                void searchUploadLocation();
            }
        });
    }

    if (applyManualCoordinatesBtn) {
        applyManualCoordinatesBtn.addEventListener('click', () => {
            const lat = manualLatitudeInput ? Number.parseFloat(manualLatitudeInput.value) : Number.NaN;
            const lng = manualLongitudeInput ? Number.parseFloat(manualLongitudeInput.value) : Number.NaN;

            if (!isValidCoordinatePair(lat, lng)) {
                showCoordinateError('Please enter valid coordinates (latitude -90 to 90, longitude -180 to 180).');
                return;
            }

            initializeUploadMap();
            setUploadCoordinates(lat, lng, { updateMap: true, centerMap: true, label: 'Manual coordinates', openPopup: true });
            updateSearchStatus('Manual coordinates applied. You can still click map to adjust.', false);
        });
    }

    [manualLatitudeInput, manualLongitudeInput].forEach((input) => {
        if (!input) {
            return;
        }

        input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                if (applyManualCoordinatesBtn) {
                    applyManualCoordinatesBtn.click();
                }
            }
        });
    });

    const existingLat = latitudeInput ? Number.parseFloat(latitudeInput.value) : Number.NaN;
    const existingLng = longitudeInput ? Number.parseFloat(longitudeInput.value) : Number.NaN;
    if (isValidCoordinatePair(existingLat, existingLng)) {
        setUploadCoordinates(existingLat, existingLng, { updateMap: false });
    }

    const imageInput = document.getElementById('imageInput');
    const imagePreview = document.getElementById('imagePreview');
    const uploadDropArea = document.getElementById('uploadDropArea');
    const browseImageBtn = document.getElementById('browseImageBtn');
    const imageInputError = document.getElementById('imageInputError');

    const previewImage = (file) => {
        if (!file || !file.type.startsWith('image/')) {
            return;
        }

        const reader = new FileReader();
        reader.onload = (event) => {
            if (imagePreview) {
                imagePreview.src = event.target.result;
                imagePreview.classList.remove('d-none');
            }
            if (imageInputError) {
                imageInputError.classList.add('d-none');
            }
        };
        reader.readAsDataURL(file);
    };

    if (browseImageBtn && imageInput) {
        browseImageBtn.addEventListener('click', () => imageInput.click());
    }

    if (uploadDropArea && imageInput) {
        uploadDropArea.addEventListener('click', (event) => {
            if (event.target.id !== 'browseImageBtn') {
                imageInput.click();
            }
        });

        uploadDropArea.addEventListener('dragover', (event) => {
            event.preventDefault();
            uploadDropArea.classList.add('drag-over');
        });

        uploadDropArea.addEventListener('dragleave', () => {
            uploadDropArea.classList.remove('drag-over');
        });

        uploadDropArea.addEventListener('drop', (event) => {
            event.preventDefault();
            uploadDropArea.classList.remove('drag-over');

            if (event.dataTransfer.files.length > 0) {
                const droppedFile = event.dataTransfer.files[0];
                const dt = new DataTransfer();
                dt.items.add(droppedFile);
                imageInput.files = dt.files;
                previewImage(droppedFile);
            }
        });
    }

    if (imageInput) {
        imageInput.addEventListener('change', () => {
            if (imageInput.files && imageInput.files[0]) {
                previewImage(imageInput.files[0]);
            }
        });
    }

    document.querySelectorAll('form[data-validate]').forEach((form) => {
        form.addEventListener('submit', (event) => {
            const valid = form.checkValidity();

            if (!valid) {
                event.preventDefault();
                event.stopPropagation();
                form.classList.add('shake-invalid');
                setTimeout(() => form.classList.remove('shake-invalid'), 350);

                if (imageInput && !imageInput.files.length && imageInputError) {
                    imageInputError.classList.remove('d-none');
                }
            }

            form.classList.add('was-validated');
        }, false);
    });

    const bindCapsLockWarning = (inputId, warningId) => {
        const input = document.getElementById(inputId);
        const warning = document.getElementById(warningId);

        if (!input || !warning) {
            return;
        }

        const updateCaps = (event) => {
            if (event.getModifierState && event.getModifierState('CapsLock')) {
                warning.classList.remove('d-none');
            } else {
                warning.classList.add('d-none');
            }
        };

        input.addEventListener('keyup', updateCaps);
        input.addEventListener('keydown', updateCaps);
        input.addEventListener('blur', () => warning.classList.add('d-none'));
    };

    document.querySelectorAll('[data-toggle-password]').forEach((button) => {
        const targetId = button.getAttribute('data-target');
        const targetInput = document.getElementById(targetId);

        if (!targetInput) {
            return;
        }

        button.addEventListener('click', () => {
            const isPassword = targetInput.type === 'password';
            targetInput.type = isPassword ? 'text' : 'password';

            const icon = button.querySelector('i');
            if (icon) {
                icon.classList.toggle('bi-eye', !isPassword);
                icon.classList.toggle('bi-eye-slash', isPassword);
            }

            button.setAttribute('aria-label', isPassword ? 'Hide password' : 'Show password');
        });
    });

    bindCapsLockWarning('id_password', 'id_password_caps_warning');
    bindCapsLockWarning('id_password1', 'id_password1_caps_warning');
    bindCapsLockWarning('id_password2', 'id_password2_caps_warning');

    const revealElements = document.querySelectorAll('.reveal-on-scroll');
    if (revealElements.length) {
        if ('IntersectionObserver' in window) {
            const revealObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('is-visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, { 
                threshold: 0.05,
                rootMargin: '0px 0px -80px 0px'
            });

            revealElements.forEach((element) => revealObserver.observe(element));
        } else {
            revealElements.forEach((element) => element.classList.add('is-visible'));
        }
    }

    const smoothLinks = document.querySelectorAll('a.grid-scroll-link[href^="#"]');
    smoothLinks.forEach((link) => {
        link.addEventListener('click', (event) => {
            const targetSelector = link.getAttribute('href');
            const target = targetSelector ? document.querySelector(targetSelector) : null;
            if (target) {
                event.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    const initializeDescriptionToggles = () => {
        const toggles = document.querySelectorAll('.js-description-toggle');

        toggles.forEach((toggleButton) => {
            const parent = toggleButton.parentElement;
            if (!parent) {
                return;
            }

            const descriptionNode = parent.querySelector('.js-expandable-description');
            if (!descriptionNode) {
                return;
            }

            const descriptionBlock = descriptionNode.closest('.js-description-block');

            const fullText = (descriptionNode.dataset.fullText || descriptionNode.textContent || '').trim();
            const configuredLimit = Number.parseInt(descriptionNode.dataset.charLimit || '', 10);
            const shortLimit = Number.isFinite(configuredLimit) && configuredLimit > 0 ? configuredLimit : 130;
            const shortText = fullText.length > shortLimit
                ? `${fullText.slice(0, shortLimit).trimEnd()}...`
                : fullText;

            if (fullText.length <= shortLimit) {
                descriptionNode.textContent = fullText;
                toggleButton.classList.add('d-none');
                return;
            }

            let isExpanded = false;

            const renderState = () => {
                descriptionNode.textContent = isExpanded ? fullText : shortText;
                toggleButton.textContent = isExpanded ? 'View less' : 'View more';
                toggleButton.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
                if (descriptionBlock) {
                    descriptionBlock.classList.toggle('is-expanded', isExpanded);
                }
            };

            toggleButton.addEventListener('click', () => {
                isExpanded = !isExpanded;
                renderState();
            });

            renderState();
        });
    };

    initializeDescriptionToggles();

    const stateCardButtons = document.querySelectorAll('[data-state-card]');
    const stateSpotlightTitle = document.getElementById('stateSpotlightTitle');
    const stateSpotlightCopy = document.getElementById('stateSpotlightCopy');
    const stateSpotlightHighlight = document.getElementById('stateSpotlightHighlight');
    const stateSpotlightFocus = document.getElementById('stateSpotlightFocus');
    const stateSpotlightDiscoverLink = document.getElementById('stateSpotlightDiscoverLink');

    const setStateSpotlight = (button) => {
        if (!stateSpotlightTitle || !stateSpotlightCopy || !stateSpotlightHighlight || !stateSpotlightFocus) {
            return;
        }

        stateCardButtons.forEach((item) => {
            item.classList.toggle('is-active', item === button);
            item.setAttribute('aria-pressed', item === button ? 'true' : 'false');
        });

        stateSpotlightTitle.textContent = button.dataset.stateTitle || '';
        stateSpotlightCopy.textContent = button.dataset.stateCopy || '';
        stateSpotlightHighlight.textContent = button.dataset.stateHighlight || '';
        stateSpotlightFocus.textContent = button.dataset.stateFocus || '';

        if (stateSpotlightDiscoverLink) {
            const slug = (button.dataset.stateSlug || (button.dataset.stateTitle || '').toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, ''));
            stateSpotlightDiscoverLink.href = `/discover/state/${slug}/`;
            const labelSpan = stateSpotlightDiscoverLink.querySelector('span');
            if (labelSpan) {
                labelSpan.textContent = button.dataset.stateTitle || '';
            }
        }
    };

    stateCardButtons.forEach((button) => {
        button.addEventListener('click', () => setStateSpotlight(button));
    });

    if (stateCardButtons.length) {
        setStateSpotlight(document.querySelector('[data-state-card].is-active') || stateCardButtons[0]);
    }

    const revealCards = document.querySelectorAll('.reveal-card');
    if (revealCards.length) {
        if ('IntersectionObserver' in window) {
            const cardObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach((entry) => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('is-visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, { 
                threshold: 0.02,
                rootMargin: '0px 0px -60px 0px'
            });

            revealCards.forEach((card) => cardObserver.observe(card));
        } else {
            revealCards.forEach((card) => card.classList.add('is-visible'));
        }
    }

    const getCsrfToken = () => {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content') || '';
        }
        const cookieValue = document.cookie
            .split('; ')
            .find((cookie) => cookie.startsWith('csrftoken='));
        return cookieValue ? decodeURIComponent(cookieValue.split('=')[1]) : '';
    };

    document.querySelectorAll('.js-upvote-btn').forEach((button) => {
        button.addEventListener('click', async () => {
            const upvoteUrl = button.getAttribute('data-upvote-url');
            const card = button.closest('.discover-gallery-card');
            const countNode = card ? card.querySelector('[data-upvote-count]') : null;
            const actionLabelNode = button.querySelector('span');

            if (!upvoteUrl || button.disabled) {
                return;
            }

            button.disabled = true;

            try {
                const response = await window.fetch(upvoteUrl, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'X-CSRFToken': getCsrfToken(),
                        'X-Requested-With': 'XMLHttpRequest',
                        Accept: 'application/json',
                    },
                });
                const payload = await response.json().catch(() => ({}));

                if (!response.ok) {
                    button.setAttribute('title', payload.detail || 'Unable to upvote right now.');
                    button.disabled = false;
                    return;
                }

                if (countNode && Number.isFinite(Number(payload.upvote_count))) {
                    countNode.textContent = String(payload.upvote_count);
                    countNode.classList.remove('upvote-pop');
                    // Force reflow so the animation can be replayed.
                    void countNode.offsetWidth;
                    countNode.classList.add('upvote-pop');
                }

                button.classList.add('is-upvoted');
                if (actionLabelNode) {
                    actionLabelNode.textContent = 'Upvoted';
                }
                button.setAttribute('title', payload.detail || 'Upvoted');
                button.disabled = true;
            } catch (error) {
                button.setAttribute('title', 'Unable to upvote right now. Please try again.');
                button.disabled = false;
            }
        });
    });
});


