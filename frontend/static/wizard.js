/**
 * MVidarr Installation Wizard
 * v1.0.0 - Issue #163
 *
 * Client-side controller for the first-run installation wizard.
 * Manages step navigation, form validation, API communication, and progress tracking.
 */

// Wizard state
const wizardState = {
    currentStep: 0,
    totalSteps: 6,
    completedSteps: [],
    config: {
        admin: {},
        directories: {},
        apis: {},
        import: {}
    },
    directoryValidated: false,
    importJobId: null
};

// Initialize wizard on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('🧙 Wizard initialized');
    loadWizardState();
    updateProgress();
});

// ============================================================================
// NAVIGATION
// ============================================================================

async function nextStep() {
    // Map frontend step indices to backend step names
    const stepNames = ['welcome', 'admin_account', 'directories', 'api_config', 'video_import', 'complete'];
    const currentStepName = stepNames[wizardState.currentStep];

    // Complete current step on backend before advancing (except complete step)
    if (currentStepName && currentStepName !== 'complete') {
        try {
            console.log(`Completing step: ${currentStepName}`);

            // Get config data for current step from wizardState
            let stepConfig = {};
            if (currentStepName === 'admin_account' && wizardState.config.admin) {
                stepConfig = wizardState.config.admin;
            } else if (currentStepName === 'directories' && wizardState.config.directories) {
                stepConfig = wizardState.config.directories;
            } else if (currentStepName === 'api_config' && wizardState.config.apis) {
                stepConfig = wizardState.config.apis;
            }

            await completeStep(currentStepName, stepConfig);
            console.log(`✅ Step ${currentStepName} completed successfully`);
        } catch (error) {
            console.error(`❌ Failed to complete step ${currentStepName}:`, error);
            // Show detailed error to user
            const errorMsg = error.message || 'Unknown error occurred';
            alert(`Failed to complete "${currentStepName}" step:\n\n${errorMsg}\n\nCheck browser console for details.`);
            return; // Don't advance if step completion fails
        }
    }

    // Now advance to next step in UI
    if (wizardState.currentStep < wizardState.totalSteps - 1) {
        wizardState.currentStep++;
        showStep(wizardState.currentStep);
        updateProgress();
        saveWizardState();
    }
}

function previousStep() {
    if (wizardState.currentStep > 0) {
        wizardState.currentStep--;
        showStep(wizardState.currentStep);
        updateProgress();
    }
}

function showStep(stepIndex) {
    // Hide all steps
    document.querySelectorAll('.wizard-step').forEach(step => {
        step.classList.remove('active');
    });

    // Show current step
    const steps = ['welcome', 'admin', 'directories', 'apis', 'import', 'complete'];
    const stepElement = document.getElementById(`step-${steps[stepIndex]}`);
    if (stepElement) {
        stepElement.classList.add('active');
    }

    // Update progress steps
    document.querySelectorAll('.progress-step').forEach((step, index) => {
        step.classList.remove('active', 'completed');
        if (index === stepIndex) {
            step.classList.add('active');
        } else if (index < stepIndex) {
            step.classList.add('completed');
        }
    });

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateProgress() {
    const progressPercent = (wizardState.currentStep / (wizardState.totalSteps - 1)) * 100;
    const progressLine = document.getElementById('progressLineFill');
    if (progressLine) {
        progressLine.style.width = `${progressPercent}%`;
    }
}

// ============================================================================
// WIZARD STATE MANAGEMENT
// ============================================================================

async function loadWizardState() {
    try {
        const response = await fetch('/api/wizard/status');
        if (response.ok) {
            const data = await response.json();
            console.log('📊 Loaded wizard state:', data);

            // Map backend step names to frontend step indices
            const stepNames = ['welcome', 'admin_account', 'directories', 'api_config', 'video_import', 'complete'];
            const currentStepIndex = stepNames.indexOf(data.current_step);

            // Sync UI with server state
            if (currentStepIndex !== -1) {
                wizardState.currentStep = currentStepIndex;
                showStep(currentStepIndex);
                updateProgress();
                console.log(`🎯 Synced UI to step: ${data.current_step} (index ${currentStepIndex})`);
            }

            // Update local state from server
            if (data.config_data) {
                wizardState.config = { ...wizardState.config, ...data.config_data };
            }

            // Store import job ID if present
            if (data.import_job_id) {
                wizardState.importJobId = data.import_job_id;
            }
        }
    } catch (error) {
        console.error('Error loading wizard state:', error);
    }
}

async function saveWizardState() {
    // NOTE: Wizard state is automatically saved on the server side
    // when steps are completed via the /api/wizard/steps/{step}/complete endpoint.
    // This function is kept for backwards compatibility but does nothing.
    console.log('Wizard state saved on server via step completion endpoints');
}

async function completeStep(stepName, configData = {}) {
    const response = await fetch(`/api/wizard/steps/${stepName}/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            config_data: configData
        })
    });

    if (response.ok) {
        const data = await response.json();
        console.log(`✅ Step ${stepName} completed:`, data);
        return true;
    } else {
        const error = await response.json();
        console.error(`❌ Failed to complete step ${stepName}:`, error);
        throw new Error(error.detail || `Failed to complete step ${stepName}`);
    }
}

// ============================================================================
// STEP 2: ADMIN ACCOUNT
// ============================================================================

async function submitAdminForm() {
    const form = document.getElementById('adminForm');
    const submitBtn = document.getElementById('adminSubmitBtn');

    // Clear previous errors
    clearFormErrors();

    // Get form values
    const username = document.getElementById('username').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    // Validate form
    let isValid = true;

    if (!username || username.length < 3) {
        showError('usernameError', 'Username must be at least 3 characters');
        isValid = false;
    }

    if (!email || !isValidEmail(email)) {
        showError('emailError', 'Please enter a valid email address');
        isValid = false;
    }

    if (!password || password.length < 8) {
        showError('passwordError', 'Password must be at least 8 characters');
        isValid = false;
    }

    if (password !== confirmPassword) {
        showError('confirmPasswordError', 'Passwords do not match');
        isValid = false;
    }

    if (!isValid) {
        return;
    }

    // Disable button and show loading
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Creating account...';

    try {
        // Create user account via wizard API (no authentication required)
        const response = await fetch('/api/wizard/create-admin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: username,
                email: email,
                password: password
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Save to wizard state
            wizardState.config.admin = { username, email, user_id: data.user_id };
            saveWizardState();

            // Move to next step (nextStep will handle completing the step on backend)
            nextStep();
        } else {
            // Handle error response - route to correct field based on error message
            const errorMessage = data.message || 'Failed to create admin account';

            // Check if error is password-related
            if (errorMessage.toLowerCase().includes('password')) {
                showError('passwordError', errorMessage);
            }
            // Check if error is email-related
            else if (errorMessage.toLowerCase().includes('email')) {
                showError('emailError', errorMessage);
            }
            // Check if error is username-related or default
            else {
                showError('usernameError', errorMessage);
            }
        }
    } catch (error) {
        console.error('Error creating admin account:', error);
        showError('usernameError', 'An error occurred. Please try again.');
    } finally {
        // Re-enable button
        submitBtn.disabled = false;
        submitBtn.innerHTML = 'Continue <iconify-icon icon="mdi:arrow-right"></iconify-icon>';
    }
}

// ============================================================================
// STEP 3: DIRECTORIES
// ============================================================================

async function validateDirectory() {
    const pathInput = document.getElementById('musicVideosPath');
    const path = pathInput.value.trim();
    const validateBtn = document.getElementById('validateDirBtn');
    const submitBtn = document.getElementById('directoriesSubmitBtn');
    const resultsDiv = document.getElementById('directoryResults');

    if (!path) {
        showError('directoryError', 'Please enter a directory path');
        return;
    }

    // Clear previous validation
    clearError('directoryError');
    resultsDiv.classList.add('hidden');

    // Disable button and show loading
    validateBtn.disabled = true;
    validateBtn.innerHTML = '<span class="spinner"></span> Validating...';

    try {
        const response = await fetch('/api/wizard/validate-directory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path })
        });

        const data = await response.json();

        if (data.valid) {
            // Show success
            resultsDiv.classList.remove('hidden');
            document.getElementById('videoCount').textContent = data.video_count || 0;
            document.getElementById('importVideoCount').textContent = data.video_count || 0;

            // Enable submit button
            submitBtn.disabled = false;
            wizardState.directoryValidated = true;
            wizardState.config.directories = { path: path, video_count: data.video_count };
        } else {
            // Show error
            showError('directoryError', data.error || 'Directory validation failed');
            submitBtn.disabled = true;
            wizardState.directoryValidated = false;
        }
    } catch (error) {
        console.error('Error validating directory:', error);
        showError('directoryError', 'An error occurred while validating the directory');
        submitBtn.disabled = true;
        wizardState.directoryValidated = false;
    } finally {
        // Re-enable button
        validateBtn.disabled = false;
        validateBtn.innerHTML = '<iconify-icon icon="mdi:check-circle"></iconify-icon> Validate Directory';
    }
}

async function submitDirectories() {
    if (!wizardState.directoryValidated) {
        showError('directoryError', 'Please validate the directory first');
        return;
    }

    // Config already saved in wizardState.config.directories (line 291)
    // nextStep() will handle completing the step on backend
    saveWizardState();
    nextStep();
}

// ============================================================================
// STEP 4: API CONFIGURATION
// ============================================================================

async function testIMVDb() {
    const apiKeyInput = document.getElementById('imvdbApiKey');
    const apiKey = apiKeyInput.value.trim();
    const testBtn = document.getElementById('testIMVDbBtn');
    const validationDiv = document.getElementById('imvdbValidation');

    if (!apiKey) {
        showError('imvdbError', 'Please enter an API key');
        return;
    }

    // Clear previous validation
    clearError('imvdbError');
    validationDiv.innerHTML = '';

    // Disable button and show loading
    testBtn.disabled = true;
    testBtn.innerHTML = '<span class="spinner"></span> Testing...';

    try {
        const response = await fetch('/api/wizard/test-api', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_type: 'imvdb',
                api_key: apiKey
            })
        });

        const data = await response.json();

        if (data.success) {
            // Show success
            validationDiv.innerHTML = `
                <div class="validation-badge success">
                    <iconify-icon icon="mdi:check-circle"></iconify-icon>
                    ${data.message}
                </div>
            `;
            wizardState.config.apis.imvdb = apiKey;
        } else {
            // Show error
            validationDiv.innerHTML = `
                <div class="validation-badge error">
                    <iconify-icon icon="mdi:alert-circle"></iconify-icon>
                    ${data.message}
                </div>
            `;
        }
    } catch (error) {
        console.error('Error testing IMVDb API:', error);
        validationDiv.innerHTML = `
            <div class="validation-badge error">
                <iconify-icon icon="mdi:alert-circle"></iconify-icon>
                Connection test failed
            </div>
        `;
    } finally {
        // Re-enable button
        testBtn.disabled = false;
        testBtn.innerHTML = '<iconify-icon icon="mdi:test-tube"></iconify-icon> Test Connection';
    }
}

async function submitAPIs() {
    const imvdbKey = document.getElementById('imvdbApiKey').value.trim();
    const youtubeCookies = document.getElementById('youtubeCookies').value.trim();

    // Save API configuration (both optional)
    wizardState.config.apis = {
        imvdb: imvdbKey || null,
        youtube: youtubeCookies || null
    };

    // Save config and advance (nextStep will handle completing the step)
    saveWizardState();
    nextStep();
}

// ============================================================================
// STEP 5: VIDEO IMPORT
// ============================================================================

async function startImport() {
    const importType = document.querySelector('input[name="importType"]:checked').value;

    if (importType === 'skip') {
        // Skip import
        wizardState.config.import.skipped = true;
        saveWizardState();
        nextStep();
        return;
    }

    // Hide options, show progress
    document.getElementById('importOptions').classList.add('hidden');
    document.getElementById('importProgress').classList.remove('hidden');
    document.getElementById('importBackBtn').disabled = true;

    // Reset error section
    document.getElementById('importErrorSection').classList.add('hidden');
    document.getElementById('importErrorList').innerHTML = '';

    const fetchMetadata = importType === 'full';
    const directory = wizardState.config.directories.path;

    try {
        // Start import job
        const response = await fetch('/api/wizard/import/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                directory: directory,
                fetch_metadata: fetchMetadata,
                max_files: null  // Import all files
            })
        });

        const data = await response.json();

        if (data.success) {
            wizardState.importJobId = data.job_id;
            console.log(`✅ Import job started: ${data.job_id}`);

            // Start polling for progress
            pollImportProgress();
        } else {
            throw new Error('Failed to start import job');
        }
    } catch (error) {
        console.error('Error starting import:', error);
        alert('Failed to start import. Please try again.');

        // Show options again
        document.getElementById('importOptions').classList.remove('hidden');
        document.getElementById('importProgress').classList.add('hidden');
        document.getElementById('importBackBtn').disabled = false;
    }
}

async function pollImportProgress() {
    if (!wizardState.importJobId) {
        return;
    }

    try {
        // Poll job status from standard Celery endpoint
        const response = await fetch(`/api/jobs/${wizardState.importJobId}`);
        const job = await response.json();

        if (!job) {
            throw new Error('Job not found');
        }

        // Extract progress data (can be in job.progress while running, or job.result when complete)
        const progressData = job.progress || job.result || {};
        const progressPercent = progressData.progress || progressData.percent || 0;
        const processed = progressData.videos_processed || 0;
        const success = progressData.videos_success || 0;
        const failed = progressData.videos_failed || 0;
        const currentFile = progressData.current_file || '';
        const errors = progressData.errors || [];

        // Debug logging
        console.log(`📊 Job status: ${job.status}, progress: ${progressPercent}%, processed: ${processed}, success: ${success}, failed: ${failed}`);
        if (currentFile) {
            console.log(`   📄 Current file: ${currentFile}`);
        }
        if (errors.length > 0) {
            console.log(`   ❌ Errors: ${errors.length} files failed`, errors);
        }

        // Update progress UI
        document.getElementById('importProgressBar').style.width = `${progressPercent}%`;
        document.getElementById('importProgressText').textContent = `${Math.round(progressPercent)}%`;
        document.getElementById('importProcessed').textContent = processed;
        document.getElementById('importSuccess').textContent = success;
        document.getElementById('importFailed').textContent = failed;

        // Update current file display
        if (currentFile) {
            document.getElementById('importCurrentFile').textContent = `Processing: ${currentFile}`;
        } else if (progressPercent === 100) {
            document.getElementById('importCurrentFile').textContent = 'Import complete';
        } else if (progressData.message) {
            document.getElementById('importCurrentFile').textContent = progressData.message;
        }

        // Display error details if any errors occurred
        if (errors && errors.length > 0) {
            displayImportErrors(errors);
        } else if (failed > 0) {
            // Show error section if no detailed errors but had failures
            document.getElementById('importErrorSection').classList.remove('hidden');
            document.getElementById('importErrorList').innerHTML = `
                <div style="padding: 0.5rem; color: var(--wizard-text-secondary);">
                    ${failed} file(s) failed to import. Check logs for details.
                </div>
            `;
        }

        // Check if complete (Celery statuses: success, failure, progress, pending)
        if (job.status === 'success' || job.status === 'failure' || job.status === 'completed' || job.status === 'failed') {
            finishImport(success);
        } else {
            // Continue polling
            setTimeout(pollImportProgress, 2000);  // Poll every 2 seconds
        }
    } catch (error) {
        console.error('Error polling import progress:', error);
        // Retry polling
        setTimeout(pollImportProgress, 5000);
    }
}

function displayImportErrors(errors) {
    const errorSection = document.getElementById('importErrorSection');
    const errorList = document.getElementById('importErrorList');

    if (!errors || errors.length === 0) {
        errorSection.classList.add('hidden');
        return;
    }

    // Show error section
    errorSection.classList.remove('hidden');

    // Build error list HTML
    const errorItems = errors.map(err => `
        <div style="padding: 0.5rem; border-bottom: 1px solid var(--wizard-border, #ddd); background: white; margin-bottom: 0.25rem; border-radius: 4px;">
            <div style="font-weight: 500; color: var(--wizard-error, #d32f2f); margin-bottom: 0.25rem;">
                <iconify-icon icon="mdi:file-alert" style="font-size: 1rem;"></iconify-icon>
                ${err.file || 'Unknown file'}
            </div>
            <div style="color: var(--wizard-text-secondary, #666); font-size: 0.85rem; padding-left: 1.25rem;">
                ${err.error || 'Unknown error'}
            </div>
        </div>
    `).join('');

    errorList.innerHTML = errorItems;
}

function finishImport(videoCount) {
    // Hide progress, show complete
    document.getElementById('importProgress').classList.add('hidden');
    document.getElementById('importComplete').classList.remove('hidden');
    document.getElementById('importFinalCount').textContent = videoCount;

    // Enable complete button
    document.getElementById('importCompleteBtn').disabled = false;

    // Save import results
    wizardState.config.import = {
        completed: true,
        video_count: videoCount
    };

    console.log('✅ Import completed');
}

async function completeImport() {
    // Config already saved during import process
    // nextStep() will handle completing the step
    saveWizardState();
    nextStep();

    // Update completion summary
    updateCompletionSummary();
}

function updateCompletionSummary() {
    // Update API summary
    const hasAPIs = wizardState.config.apis.imvdb || wizardState.config.apis.youtube;
    if (!hasAPIs) {
        document.getElementById('summaryAPIs').innerHTML = `
            <iconify-icon icon="mdi:information" style="color: var(--wizard-warning);"></iconify-icon>
            API keys not configured (optional)
        `;
    }

    // Update import summary
    if (wizardState.config.import.skipped) {
        document.getElementById('summaryImportText').textContent = 'Import skipped (you can import later)';
        document.getElementById('summaryImport').querySelector('iconify-icon').style.color = 'var(--wizard-warning)';
    } else {
        document.getElementById('summaryImportText').textContent =
            `${wizardState.config.import.video_count || 0} videos imported`;
    }
}

// ============================================================================
// WIZARD CONTROLS
// ============================================================================

async function skipWizard() {
    if (confirm('Are you sure you want to skip the setup wizard? You can configure MVidarr manually later.')) {
        try {
            const response = await fetch('/api/wizard/skip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });

            if (response.ok) {
                console.log('✅ Wizard skipped');
                window.location.href = '/dashboard';
            }
        } catch (error) {
            console.error('Error skipping wizard:', error);
            alert('Failed to skip wizard. Please try again.');
        }
    }
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

function showError(errorId, message) {
    const errorElement = document.getElementById(errorId);
    if (errorElement) {
        errorElement.textContent = message;
        errorElement.classList.add('show');

        // Also mark input as error
        const inputId = errorId.replace('Error', '');
        const inputElement = document.getElementById(inputId);
        if (inputElement) {
            inputElement.classList.add('error');
        }
    }
}

function clearError(errorId) {
    const errorElement = document.getElementById(errorId);
    if (errorElement) {
        errorElement.textContent = '';
        errorElement.classList.remove('show');

        // Also remove error class from input
        const inputId = errorId.replace('Error', '');
        const inputElement = document.getElementById(inputId);
        if (inputElement) {
            inputElement.classList.remove('error');
        }
    }
}

function clearFormErrors() {
    document.querySelectorAll('.form-error').forEach(error => {
        error.textContent = '';
        error.classList.remove('show');
    });
    document.querySelectorAll('.form-input').forEach(input => {
        input.classList.remove('error');
    });
}

// ============================================================================
// Directory Browser Functions
// ============================================================================

let currentBrowsePath = '/';

async function openDirectoryBrowser() {
    const modal = document.getElementById('directoryBrowserModal');
    modal.style.display = 'flex';

    // Start from the current value or root
    const currentValue = document.getElementById('musicVideosPath').value;
    currentBrowsePath = currentValue || '/';

    await loadDirectory(currentBrowsePath);
}

function closeDirectoryBrowser() {
    const modal = document.getElementById('directoryBrowserModal');
    modal.style.display = 'none';
}

function selectCurrentDirectory() {
    document.getElementById('musicVideosPath').value = currentBrowsePath;
    closeDirectoryBrowser();

    // Clear validation so user can re-validate with new path
    document.getElementById('directoriesSubmitBtn').disabled = true;
    document.getElementById('directoryResults').classList.add('hidden');
}

async function loadDirectory(path) {
    const directoryList = document.getElementById('directoryList');
    const currentPathInput = document.getElementById('currentPath');

    currentPathInput.value = path;
    currentBrowsePath = path;

    directoryList.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);"><span class="spinner"></span> Loading...</div>';

    try {
        const response = await fetch(`/api/filesystem/browse?path=${encodeURIComponent(path)}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load directory');
        }

        let html = '';

        // Add parent directory link if not at root
        if (data.parent_path) {
            html += `
                <div class="directory-item" onclick="loadDirectory('${escapeHtml(data.parent_path)}')">
                    <iconify-icon icon="mdi:arrow-up" style="font-size: 1.5rem; color: var(--primary-color);"></iconify-icon>
                    <div class="directory-info">
                        <div class="directory-name">..</div>
                        <div class="directory-meta">Parent Directory</div>
                    </div>
                </div>
            `;
        }

        // Add directories
        if (data.entries.length === 0) {
            html += '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">No subdirectories found</div>';
        } else {
            data.entries.forEach(entry => {
                const videoCountText = entry.video_count !== null ? `${entry.video_count} videos` : '';
                html += `
                    <div class="directory-item" onclick="loadDirectory('${escapeHtml(entry.path)}')">
                        <iconify-icon icon="mdi:folder" style="font-size: 1.5rem; color: var(--warning-color);"></iconify-icon>
                        <div class="directory-info">
                            <div class="directory-name">${escapeHtml(entry.name)}</div>
                            ${videoCountText ? `<div class="directory-meta">${videoCountText}</div>` : ''}
                        </div>
                    </div>
                `;
            });
        }

        directoryList.innerHTML = html;

    } catch (error) {
        console.error('Error loading directory:', error);
        directoryList.innerHTML = `
            <div style="padding: 2rem; text-align: center;">
                <div style="color: var(--danger-color); margin-bottom: 0.5rem;">
                    <iconify-icon icon="mdi:alert-circle" style="font-size: 2rem;"></iconify-icon>
                </div>
                <div style="color: var(--text-secondary);">${escapeHtml(error.message)}</div>
            </div>
        `;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

console.log('🧙 Wizard controller loaded successfully');
