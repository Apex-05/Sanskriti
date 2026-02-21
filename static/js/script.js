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

    const mapContainer = document.getElementById('indiaMap');
    if (mapContainer && typeof L !== 'undefined') {
        const indiaMap = L.map('indiaMap', { zoomControl: true }).setView([22.5937, 78.9629], 5);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(indiaMap);

        L.marker([22.5937, 78.9629])
            .addTo(indiaMap)
            .bindPopup('Cultural uploads across India will appear here.')
            .openPopup();

        setTimeout(() => {
            indiaMap.invalidateSize();
        }, 150);
    }

    const uploadMapModal = document.getElementById('uploadMapModal');
    const uploadMapEl = document.getElementById('uploadMap');
    const coordinatesLabel = document.getElementById('selectedCoordinates');
    const latitudeInput = document.getElementById('latitude');
    const longitudeInput = document.getElementById('longitude');

    let uploadMap;
    let uploadMarker;

    if (uploadMapModal && uploadMapEl && typeof L !== 'undefined') {
        uploadMapModal.addEventListener('shown.bs.modal', () => {
            if (!uploadMap) {
                uploadMap = L.map('uploadMap').setView([22.5937, 78.9629], 5);

                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    maxZoom: 19,
                    attribution: '&copy; OpenStreetMap contributors'
                }).addTo(uploadMap);

                uploadMap.on('click', (event) => {
                    const { lat, lng } = event.latlng;

                    if (uploadMarker) {
                        uploadMarker.setLatLng([lat, lng]);
                    } else {
                        uploadMarker = L.marker([lat, lng]).addTo(uploadMap);
                    }

                    if (latitudeInput) latitudeInput.value = lat.toFixed(6);
                    if (longitudeInput) longitudeInput.value = lng.toFixed(6);

                    if (coordinatesLabel) {
                        coordinatesLabel.textContent = `Lat: ${lat.toFixed(6)}, Lng: ${lng.toFixed(6)}`;
                    }
                });
            }

            setTimeout(() => {
                uploadMap.invalidateSize();
            }, 150);
        });
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
});


