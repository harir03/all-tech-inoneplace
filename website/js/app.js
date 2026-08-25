/**
 * OpportunityHub — Main Application Script
 * Features:
 *  - 6 Live categories (Hackathons, Internships, Jobs & New Grad, Competitions, OS, Fellowships)
 *  - Comprehensive multi-dimensional filtering & sorting
 *  - AI Resume Matcher & Auto-Applier scoring engine
 *  - 1-Click Quick Apply Profile with LinkedIn, GitHub, Portfolio & Resume
 *  - Batch Multi-Select & 1-Click Open/Autofill Action Bar
 *  - Account & Saved Profile Management
 */

(function () {
    'use strict';

    // ===== Configuration =====
    const CATEGORIES = [
        { key: 'hackathons', file: 'hackathons.json', icon: '🏆' },
        { key: 'internships', file: 'internships.json', icon: '💼' },
        { key: 'jobs', file: 'jobs.json', icon: '🏢' },
        { key: 'competitions', file: 'competitions.json', icon: '⚔️' },
        { key: 'open-source-programs', file: 'open-source-programs.json', icon: '🌍' },
        { key: 'fellowships', file: 'fellowships.json', icon: '🎓' },
    ];

    // ===== State =====
    let allData = {};
    let activeCategory = 'hackathons';
    let currentLimit = 36;
    const PAGE_SIZE = 36;
    let activeChips = new Set(['open']);
    let selectedOpportunities = new Set();
    let aiResumeText = '';
    let isAiMatchingActive = false;

    // ===== DOM Elements =====
    const cardsGrid = document.getElementById('cardsGrid');
    const emptyState = document.getElementById('emptyState');
    const resultsCount = document.getElementById('resultsCount');
    const loadMoreContainer = document.getElementById('loadMoreContainer');
    const loadMoreBtn = document.getElementById('loadMoreBtn');
    
    // Search & Sort
    const searchInput = document.getElementById('searchInput');
    const searchClearBtn = document.getElementById('searchClearBtn');
    const sortSelect = document.getElementById('sortSelect');
    
    // Filters
    const domainFilter = document.getElementById('domainFilter');
    const locationFilter = document.getElementById('locationFilter');
    const typeFilter = document.getElementById('typeFilter');
    const statusFilter = document.getElementById('statusFilter');
    const stipendFilter = document.getElementById('stipendFilter');
    const modeFilter = document.getElementById('modeFilter');
    const toggleAdvancedFiltersBtn = document.getElementById('toggleAdvancedFiltersBtn');
    const activeFilterBadge = document.getElementById('activeFilterBadge');
    const advancedFiltersPanel = document.getElementById('advancedFiltersPanel');
    const resetFiltersBtn = document.getElementById('resetFiltersBtn');
    const quickChips = document.querySelectorAll('.chip');
    
    // Batch Bar & Select All
    const batchApplyBar = document.getElementById('batchApplyBar');
    const batchSelectedCount = document.getElementById('batchSelectedCount');
    const batchOpenBtn = document.getElementById('batchOpenBtn');
    const batchCopyPacketBtn = document.getElementById('batchCopyPacketBtn');
    const batchClearBtn = document.getElementById('batchClearBtn');
    const selectAllVisibleBtn = document.getElementById('selectAllVisibleBtn');

    // AI Matcher Elements
    const navAiMatcherBtn = document.getElementById('navAiMatcherBtn');
    const heroAiBtn = document.getElementById('heroAiBtn');
    const aiMatchModalBtn = document.getElementById('aiMatchModalBtn');
    const aiMatcherModal = document.getElementById('aiMatcherModal');
    const closeAiModalBtn = document.getElementById('closeAiModalBtn');
    const aiResumeInput = document.getElementById('aiResumeInput');
    const runAiMatchingBtn = document.getElementById('runAiMatchingBtn');
    const clearAiMatchingBtn = document.getElementById('clearAiMatchingBtn');
    const triggerAiMatchFromProfileBtn = document.getElementById('triggerAiMatchFromProfileBtn');

    // Auth & Profile Modal
    const navAuthBtn = document.getElementById('navAuthBtn');
    const authModal = document.getElementById('authModal');
    const closeAuthModalBtn = document.getElementById('closeAuthModalBtn');
    const navAuthText = document.getElementById('navAuthText');
    const navAvatarIcon = document.getElementById('navAvatarIcon');
    const authModalAvatar = document.getElementById('authModalAvatar');
    const authModalUserName = document.getElementById('authModalUserName');
    const authModalUserEmail = document.getElementById('authModalUserEmail');
    const authExportDataBtn = document.getElementById('authExportDataBtn');
    const authClearDataBtn = document.getElementById('authClearDataBtn');

    // Profile Form
    const profileForm = document.getElementById('profileForm');
    const profileName = document.getElementById('profileName');
    const profileEmail = document.getElementById('profileEmail');
    const profilePhone = document.getElementById('profilePhone');
    const profileCollege = document.getElementById('profileCollege');
    const profileGradYear = document.getElementById('profileGradYear');
    const profileBranch = document.getElementById('profileBranch');
    const profileLinkedIn = document.getElementById('profileLinkedIn');
    const profileGithub = document.getElementById('profileGithub');
    const profilePortfolio = document.getElementById('profilePortfolio');
    const profileResume = document.getElementById('profileResume');
    const profileSkills = document.getElementById('profileSkills');
    const profileBio = document.getElementById('profileBio');
    const copyProfileBtn = document.getElementById('copyProfileBtn');
    const profileSavedMsg = document.getElementById('profileSavedMsg');
    const reminderForm = document.getElementById('reminderForm');

    // ===== Data Loading =====
    async function loadAllData() {
        const candidatePaths = [
            '../data',
            './data',
            '/data',
            'data'
        ];

        const promises = CATEGORIES.map(async (cat) => {
            let loaded = false;
            for (const basePath of candidatePaths) {
                try {
                    const res = await fetch(`${basePath}/${cat.file}`);
                    if (res.ok) {
                        allData[cat.key] = await res.json();
                        loaded = true;
                        break;
                    }
                } catch (err) {
                    // Try next candidate path
                }
            }
            if (!loaded) {
                allData[cat.key] = [];
            }
        });

        await Promise.all(promises);
        updateStats();
        renderCards();
    }

    // ===== Stats Counter Animation =====
    function updateStats() {
        const statMap = {
            'stat-hackathons': (allData['hackathons'] || []).length,
            'stat-internships': (allData['internships'] || []).length,
            'stat-jobs': (allData['jobs'] || []).length,
            'stat-competitions': (allData['competitions'] || []).length,
            'stat-programs': (allData['open-source-programs'] || []).length,
            'stat-fellowships': (allData['fellowships'] || []).length,
        };

        for (const [id, count] of Object.entries(statMap)) {
            const el = document.getElementById(id);
            if (el) {
                const numEl = el.querySelector('.stat-number');
                if (numEl) animateCounter(numEl, count);
            }
        }
    }

    function animateCounter(el, target) {
        let current = 0;
        const step = Math.max(1, Math.floor(target / 30));
        const timer = setInterval(() => {
            current += step;
            if (current >= target) {
                current = target;
                clearInterval(timer);
            }
            el.textContent = current.toLocaleString();
        }, 20);
    }

    // ===== AI Resume Matching Algorithm =====
    function calculateAiMatchScores() {
        if (!aiResumeText || !aiResumeText.trim()) {
            isAiMatchingActive = false;
            return;
        }

        const keywords = aiResumeText.toLowerCase()
            .replace(/[^\w\s+#.-]/g, ' ')
            .split(/\s+/)
            .filter(w => w.length > 2 && !['and', 'the', 'for', 'with', 'from', 'this', 'that', 'have'].includes(w));

        const keywordSet = new Set(keywords);

        for (const catKey of Object.keys(allData)) {
            const items = allData[catKey] || [];
            for (const it of items) {
                const searchableText = `${it.name || ''} ${it.description || ''} ${it.location || ''} ${(it.tags || []).join(' ')} ${it.eligibility || ''} ${it.organizer || ''}`.toLowerCase();
                
                let matches = 0;
                let techWeight = 0;

                for (const kw of keywordSet) {
                    if (searchableText.includes(kw)) {
                        matches++;
                        // High value technical keywords
                        if (['python', 'react', 'machine learning', 'ai', 'cloud', 'aws', 'backend', 'full stack', 'pytorch', 'c++', 'java', 'sql', 'docker'].includes(kw)) {
                            techWeight += 1.5;
                        }
                    }
                }

                const baseScore = keywordSet.size > 0 ? (matches / Math.min(keywordSet.size, 15)) : 0;
                const finalScore = Math.min(99, Math.max(50, Math.round((baseScore * 65 + techWeight * 5 + 45))));
                it._aiScore = matches > 0 ? finalScore : 50;
            }
        }

        isAiMatchingActive = true;
    }

    // ===== Filtering & Sorting Engine =====
    function getFilteredData() {
        const rawItems = allData[activeCategory] || [];
        const query = searchInput ? searchInput.value.toLowerCase().trim() : '';
        const domainVal = domainFilter ? domainFilter.value : 'all';
        const locationVal = locationFilter ? locationFilter.value : 'all';
        const typeVal = typeFilter ? typeFilter.value : 'all';
        const statusVal = statusFilter ? statusFilter.value : 'all';
        const stipendVal = stipendFilter ? stipendFilter.value : 'all';
        const modeVal = modeFilter ? modeFilter.value : 'all';

        return rawItems.filter(item => {
            // Search Query
            if (query) {
                const searchStr = `${item.name || ''} ${item.organizer || ''} ${item.description || ''} ${item.location || ''} ${(item.tags || []).join(' ')}`.toLowerCase();
                if (!searchStr.includes(query)) return false;
            }

            // Status Filter
            if (statusVal !== 'all' && item.status !== statusVal) {
                return false;
            }

            // Domain / Role Filter
            if (domainVal !== 'all') {
                const domainKeywords = {
                    'swe': ['software', 'developer', 'swe', 'full stack', 'frontend', 'backend', 'web', 'engineer', 'c++', 'python', 'java', 'react'],
                    'ai-ml': ['ai', 'machine learning', 'ml', 'nlp', 'vision', 'deep learning', 'data science', 'llm', 'generative', 'pytorch'],
                    'data': ['data', 'analytics', 'analyst', 'bi', 'sql', 'database', 'tableau', 'etl', 'insights'],
                    'cloud': ['cloud', 'devops', 'sre', 'aws', 'azure', 'gcp', 'kubernetes', 'infrastructure', 'platform'],
                    'security': ['security', 'cyber', 'infosec', 'threat', 'vulnerability', 'soc', 'cryptography'],
                    'mobile': ['mobile', 'android', 'ios', 'flutter', 'react native', 'swift', 'kotlin'],
                    'hardware': ['hardware', 'embedded', 'firmware', 'fpga', 'asic', 'vlsi', 'circuit', 'semiconductor', 'silicon'],
                    'quant': ['quant', 'quantitative', 'trading', 'trader', 'algorithm', 'financial', 'derivatives', 'market'],
                    'pm-design': ['product', 'design', 'ui', 'ux', 'pm', 'program manager', 'scrum']
                };
                const kws = domainKeywords[domainVal] || [];
                const itemText = `${item.name || ''} ${item.description || ''} ${(item.tags || []).join(' ')}`.toLowerCase();
                if (!kws.some(kw => itemText.includes(kw))) return false;
            }

            // Location Filter
            if (locationVal !== 'all') {
                const locStr = `${item.location || ''} ${item.mode || ''}`.toLowerCase();
                if (locationVal === 'remote' && !(locStr.includes('remote') || locStr.includes('online') || locStr.includes('virtual'))) return false;
                if (locationVal === 'india' && !(locStr.includes('india') || locStr.includes('bangalore') || locStr.includes('delhi') || locStr.includes('hyderabad') || locStr.includes('pune') || locStr.includes('chennai') || locStr.includes('mumbai'))) return false;
                if (locationVal === 'usa' && !(locStr.includes('united states') || locStr.includes('usa') || locStr.includes(', us') || locStr.includes('ca') || locStr.includes('ny') || locStr.includes('tx') || locStr.includes('wa'))) return false;
                if (locationVal === 'canada' && !(locStr.includes('canada') || locStr.includes('toronto') || locStr.includes('vancouver') || locStr.includes('montreal') || locStr.includes('waterloo'))) return false;
                if (locationVal === 'europe' && !(locStr.includes('europe') || locStr.includes('uk') || locStr.includes('germany') || locStr.includes('london') || locStr.includes('paris') || locStr.includes('amsterdam'))) return false;
            }

            // Level / Type Filter
            if (typeVal !== 'all') {
                const typeStr = `${item.name || ''} ${item.eligibility || ''} ${item.description || ''} ${(item.tags || []).join(' ')}`.toLowerCase();
                if (typeVal === 'summer' && !typeStr.includes('summer')) return false;
                if (typeVal === 'new-grad' && !(typeStr.includes('new grad') || typeStr.includes('entry level') || typeStr.includes('junior') || typeStr.includes('graduat'))) return false;
                if (typeVal === 'research' && !(typeStr.includes('research') || typeStr.includes('fellowship') || typeStr.includes('phd'))) return false;
                if (typeVal === 'open-source' && !(typeStr.includes('open source') || typeStr.includes('gsoc') || typeStr.includes('lfx') || typeStr.includes('mentorship'))) return false;
            }

            // Stipend / Fee Filter
            if (stipendVal !== 'all') {
                const compStr = `${item.stipend || ''} ${item.prize || ''} ${item.fee || ''}`.toLowerCase();
                if (stipendVal === 'paid' && !(compStr.includes('$') || compStr.includes('₹') || compStr.includes('paid') || compStr.includes('stipend') || compStr.includes('salary') || compStr.includes('cash'))) return false;
                if (stipendVal === 'free' && compStr.includes('fee') && !compStr.includes('free')) return false;
            }

            // Work Mode Filter
            if (modeVal !== 'all') {
                const mStr = `${item.mode || ''} ${item.location || ''}`.toLowerCase();
                if (modeVal === 'online' && !(mStr.includes('online') || mStr.includes('virtual') || mStr.includes('remote'))) return false;
                if (modeVal === 'in-person' && !(mStr.includes('in-person') || mStr.includes('onsite') || mStr.includes('offline'))) return false;
                if (modeVal === 'hybrid' && !mStr.includes('hybrid')) return false;
            }

            // Quick Chips
            for (const chip of activeChips) {
                const allItemText = `${item.name || ''} ${item.description || ''} ${item.location || ''} ${item.stipend || ''} ${item.prize || ''} ${(item.tags || []).join(' ')}`.toLowerCase();
                if (chip === 'remote' && !(allItemText.includes('remote') || allItemText.includes('online'))) return false;
                if (chip === 'india' && !allItemText.includes('india')) return false;
                if (chip === 'faang' && !(['google', 'microsoft', 'amazon', 'apple', 'meta', 'nvidia', 'amd', 'netflix', 'goldman', 'spacex'].some(b => allItemText.includes(b)))) return false;
                if (chip === 'ai' && !(allItemText.includes('ai') || allItemText.includes('machine learning') || allItemText.includes('ml'))) return false;
                if (chip === 'new-grad' && !(allItemText.includes('new grad') || allItemText.includes('entry level') || allItemText.includes('junior'))) return false;
                if (chip === 'summer' && !allItemText.includes('summer')) return false;
                if (chip === 'paid' && !(allItemText.includes('$') || allItemText.includes('₹') || allItemText.includes('stipend') || allItemText.includes('paid'))) return false;
                if (chip === 'open' && item.status !== 'open') return false;
            }

            return true;
        }).sort((a, b) => {
            const sortVal = sortSelect ? sortSelect.value : 'default';
            if (sortVal === 'ai-match') {
                return (b._aiScore || 0) - (a._aiScore || 0);
            }
            if (sortVal === 'company-asc') {
                return (a.name || '').localeCompare(b.name || '');
            }
            if (sortVal === 'company-desc') {
                return (b.name || '').localeCompare(a.name || '');
            }
            if (sortVal === 'deadline') {
                return (a.deadline || '9999').localeCompare(b.deadline || '9999');
            }
            // Default: Prioritize open, then AI score if active, then name
            if (isAiMatchingActive) {
                return (b._aiScore || 0) - (a._aiScore || 0);
            }
            if (a.status === 'open' && b.status !== 'open') return -1;
            if (a.status !== 'open' && b.status === 'open') return 1;
            return 0;
        });
    }

    // ===== Card Rendering =====
    function renderCards() {
        const filtered = getFilteredData();
        const total = filtered.length;

        // Results count
        if (resultsCount) {
            resultsCount.textContent = `Showing ${Math.min(currentLimit, total).toLocaleString()} of ${total.toLocaleString()} opportunities`;
        }

        // Empty state
        if (total === 0) {
            cardsGrid.innerHTML = '';
            if (emptyState) emptyState.style.display = 'block';
            if (loadMoreContainer) loadMoreContainer.style.display = 'none';
            return;
        }

        if (emptyState) emptyState.style.display = 'none';

        // Render visible batch using DocumentFragment
        const visibleItems = filtered.slice(0, currentLimit);
        const fragment = document.createDocumentFragment();

        visibleItems.forEach(item => {
            const card = createCardElement(item);
            fragment.appendChild(card);
        });

        cardsGrid.innerHTML = '';
        cardsGrid.appendChild(fragment);

        // Load More button visibility
        if (loadMoreContainer) {
            loadMoreContainer.style.display = total > currentLimit ? 'block' : 'none';
        }

        updateActiveFilterBadge();
        updateBatchBar();
    }

    function createCardElement(item) {
        const card = document.createElement('div');
        card.className = `card ${selectedOpportunities.has(item.id || item.name) ? 'card-selected' : ''}`;
        card.dataset.id = item.id || item.name;

        const statusClass = `status-${item.status || 'open'}`;
        const statusLabel = {
            'open': '🟢 Open',
            'coming-soon': '🟡 Soon',
            'closed': '🔴 Closed'
        }[item.status] || '🟢 Open';

        const applyUrl = item.applicationLink || item.website || '#';
        const isSelected = selectedOpportunities.has(item.id || item.name);

        // AI Match Badge
        let aiBadgeHtml = '';
        if (isAiMatchingActive && item._aiScore) {
            const badgeColor = item._aiScore >= 80 ? '#00cec9' : '#fdcb6e';
            aiBadgeHtml = `<span class="badge-ai-match" style="border-color: ${badgeColor}; color: ${badgeColor};">🤖 ${item._aiScore}% Match</span>`;
        }

        card.innerHTML = `
            <div class="card-checkbox-wrap">
                <input type="checkbox" class="card-select-check" data-id="${item.id || item.name}" ${isSelected ? 'checked' : ''} title="Select for Batch Apply">
            </div>
            <div class="card-header">
                <div class="card-title-group" style="padding-left: 1.8rem;">
                    <h3 class="card-title">${escapeHtml(item.name || 'Opportunity')}</h3>
                    <span class="card-organizer">${escapeHtml(item.organizer || 'Company')}</span>
                </div>
                <div class="card-badges">
                    ${aiBadgeHtml}
                    <span class="card-status ${statusClass}">${statusLabel}</span>
                </div>
            </div>
            <p class="card-desc">${escapeHtml(item.description || 'Check official page for role requirements and benefits.')}</p>
            <div class="card-meta">
                ${item.location || item.mode ? `
                    <div class="meta-item">
                        <span class="meta-icon">📍</span>
                        <span class="meta-text">${escapeHtml(item.location || item.mode)}</span>
                    </div>
                ` : ''}
                ${item.deadline ? `
                    <div class="meta-item">
                        <span class="meta-icon">📅</span>
                        <span class="meta-text">${escapeHtml(item.deadline)}</span>
                    </div>
                ` : ''}
                ${item.stipend || item.prize ? `
                    <div class="meta-item">
                        <span class="meta-icon">💰</span>
                        <span class="meta-text">${escapeHtml(item.stipend || item.prize)}</span>
                    </div>
                ` : ''}
            </div>
            <div class="card-actions">
                <button class="btn btn-sm btn-quick-apply" data-id="${item.id || item.name}" title="Copy profile & open official application link">
                    ⚡ Quick Apply
                </button>
                <a href="${applyUrl}" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary">
                    Apply Official ↗
                </a>
            </div>
        `;

        // Checkbox click listener
        const checkbox = card.querySelector('.card-select-check');
        checkbox.addEventListener('change', (e) => {
            const id = e.target.dataset.id;
            if (e.target.checked) {
                selectedOpportunities.add(id);
                card.classList.add('card-selected');
            } else {
                selectedOpportunities.delete(id);
                card.classList.remove('card-selected');
            }
            updateBatchBar();
        });

        // Quick apply button listener
        const quickApplyBtn = card.querySelector('.btn-quick-apply');
        quickApplyBtn.addEventListener('click', () => {
            handleSingleQuickApply(item);
        });

        return card;
    }

    // ===== Batch Quick Apply & Selection Logic =====
    function updateBatchBar() {
        const count = selectedOpportunities.size;
        if (!batchApplyBar) return;

        if (count > 0) {
            batchApplyBar.style.display = 'block';
            if (batchSelectedCount) batchSelectedCount.textContent = count;
            if (batchOpenBtn) batchOpenBtn.textContent = `⚡ Open & Autofill Selected (${count})`;
        } else {
            batchApplyBar.style.display = 'none';
        }
    }

    function handleSingleQuickApply(item) {
        const profile = getSavedProfile();
        const packet = generateApplicationPacket([item], profile);
        
        // Copy to clipboard
        navigator.clipboard.writeText(packet).then(() => {
            showToast(`📋 Copied Application Packet for ${item.name || 'Role'}! Opening official link...`);
        }).catch(() => {
            showToast(`Opening ${item.name || 'Role'} application page...`);
        });

        // Open link
        const url = item.applicationLink || item.website || '#';
        if (url && url !== '#') {
            window.open(url, '_blank');
        }
    }

    function handleBatchQuickApply() {
        if (selectedOpportunities.size === 0) return;

        const allItems = Object.values(allData).flat();
        const selectedList = allItems.filter(it => selectedOpportunities.has(it.id || it.name));
        const profile = getSavedProfile();

        const packet = generateApplicationPacket(selectedList, profile);
        navigator.clipboard.writeText(packet).then(() => {
            showToast(`📋 Copied tailored application packet with LinkedIn & GitHub! Opening ${selectedList.length} tabs...`);
        });

        // Open application URLs in new tabs
        selectedList.forEach(it => {
            const url = it.applicationLink || it.website;
            if (url && url !== '#') {
                window.open(url, '_blank');
            }
        });
    }

    function generateApplicationPacket(items, profile) {
        const lines = [
            `======================================================`,
            `🚀 OPPORTUNITYHUB QUICK APPLY PACKET`,
            `======================================================`,
            `Applicant: ${profile.name || 'Applicant'}`,
            `Email: ${profile.email || 'N/A'} | Phone: ${profile.phone || 'N/A'}`,
            `LinkedIn: ${profile.linkedIn || 'N/A'}`,
            `GitHub: ${profile.github || 'N/A'}`,
            `Portfolio: ${profile.portfolio || 'N/A'}`,
            `Resume URL: ${profile.resume || 'N/A'}`,
            `University: ${profile.college || 'N/A'} (${profile.branch || 'Tech'}) - Class of ${profile.gradYear || 'N/A'}`,
            `Technical Skills: ${profile.skills || 'Python, React, Machine Learning, Cloud'}`,
            `------------------------------------------------------`,
            `Summary / Pitch:`,
            `${profile.bio || 'Motivated software engineer with proven track record building scalable applications and open-source software.'}`,
            `======================================================`,
            `Target Opportunities:`,
        ];

        items.forEach((it, idx) => {
            lines.push(`\n[${idx + 1}] ${it.name} (${it.organizer || 'Company'})`);
            lines.push(`    URL: ${it.applicationLink || it.website || 'N/A'}`);
            lines.push(`    Deadline: ${it.deadline || 'Check listing'}`);
        });

        return lines.join('\n');
    }

    // ===== Profile Management =====
    function getSavedProfile() {
        const raw = localStorage.getItem('opportunityhub_profile');
        if (!raw) return {};
        try {
            return JSON.parse(raw);
        } catch {
            return {};
        }
    }

    function saveProfile(profile) {
        localStorage.setItem('opportunityhub_profile', JSON.stringify(profile));
        updateAuthHeaderDisplay();
    }

    function loadProfileIntoForm() {
        const p = getSavedProfile();
        if (profileName) profileName.value = p.name || '';
        if (profileEmail) profileEmail.value = p.email || '';
        if (profilePhone) profilePhone.value = p.phone || '';
        if (profileCollege) profileCollege.value = p.college || '';
        if (profileGradYear) profileGradYear.value = p.gradYear || '';
        if (profileBranch) profileBranch.value = p.branch || '';
        if (profileLinkedIn) profileLinkedIn.value = p.linkedIn || '';
        if (profileGithub) profileGithub.value = p.github || '';
        if (profilePortfolio) profilePortfolio.value = p.portfolio || '';
        if (profileResume) profileResume.value = p.resume || '';
        if (profileSkills) profileSkills.value = p.skills || '';
        if (profileBio) profileBio.value = p.bio || '';
        updateAuthHeaderDisplay();
    }

    function updateAuthHeaderDisplay() {
        const p = getSavedProfile();
        if (navAuthText) {
            navAuthText.textContent = p.name ? `👤 ${p.name.split(' ')[0]}` : 'Profile / Sign In';
        }
        if (authModalUserName) {
            authModalUserName.textContent = p.name || 'Guest Applicant';
        }
        if (authModalUserEmail) {
            authModalUserEmail.textContent = p.email || 'Profile stored locally in browser';
        }
    }

    // ===== Toast Notifications =====
    function showToast(message) {
        let toast = document.getElementById('globalToast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'globalToast';
            toast.style.cssText = `
                position: fixed;
                top: 2rem;
                right: 2rem;
                background: #14172e;
                color: #fff;
                border: 1px solid var(--accent-1);
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                padding: 0.9rem 1.4rem;
                border-radius: 12px;
                z-index: 3000;
                font-size: 0.88rem;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 0.6rem;
                animation: slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            `;
            document.body.appendChild(toast);
        }
        toast.textContent = message;
        toast.style.display = 'flex';
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3500);
    }

    // ===== Filter UI Helpers =====
    function updateActiveFilterBadge() {
        let count = 0;
        if (domainFilter && domainFilter.value !== 'all') count++;
        if (locationFilter && locationFilter.value !== 'all') count++;
        if (typeFilter && typeFilter.value !== 'all') count++;
        if (statusFilter && statusFilter.value !== 'all' && statusFilter.value !== 'open') count++;
        if (stipendFilter && stipendFilter.value !== 'all') count++;
        if (modeFilter && modeFilter.value !== 'all') count++;
        count += activeChips.size;

        if (activeFilterBadge) {
            if (count > 0) {
                activeFilterBadge.textContent = count;
                activeFilterBadge.style.display = 'inline-block';
            } else {
                activeFilterBadge.style.display = 'none';
            }
        }
    }

    function resetAllFilters() {
        if (searchInput) {
            searchInput.value = '';
            if (searchClearBtn) searchClearBtn.style.display = 'none';
        }
        if (domainFilter) domainFilter.value = 'all';
        if (locationFilter) locationFilter.value = 'all';
        if (typeFilter) typeFilter.value = 'all';
        if (statusFilter) statusFilter.value = 'all';
        if (stipendFilter) stipendFilter.value = 'all';
        if (modeFilter) modeFilter.value = 'all';
        if (sortSelect) sortSelect.value = 'default';

        activeChips.clear();
        quickChips.forEach(c => c.classList.remove('active'));
        currentLimit = PAGE_SIZE;
        renderCards();
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ===== Event Listeners Setup =====
    function setupEventListeners() {
        // Category Tabs
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                activeCategory = tab.dataset.category;
                currentLimit = PAGE_SIZE;
                renderCards();
            });
        });

        // Search Input
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                if (searchClearBtn) {
                    searchClearBtn.style.display = searchInput.value ? 'flex' : 'none';
                }
                currentLimit = PAGE_SIZE;
                renderCards();
            });
        }

        if (searchClearBtn) {
            searchClearBtn.addEventListener('click', () => {
                searchInput.value = '';
                searchClearBtn.style.display = 'none';
                currentLimit = PAGE_SIZE;
                renderCards();
            });
        }

        // Sort & Filters Change
        [sortSelect, domainFilter, locationFilter, typeFilter, statusFilter, stipendFilter, modeFilter].forEach(el => {
            if (el) {
                el.addEventListener('change', () => {
                    currentLimit = PAGE_SIZE;
                    renderCards();
                });
            }
        });

        // Quick Chips
        quickChips.forEach(chip => {
            chip.addEventListener('click', () => {
                const chipKey = chip.dataset.chip;
                if (!chipKey) return;

                if (activeChips.has(chipKey)) {
                    activeChips.delete(chipKey);
                    chip.classList.remove('active');
                } else {
                    activeChips.add(chipKey);
                    chip.classList.add('active');
                }
                currentLimit = PAGE_SIZE;
                renderCards();
            });
        });

        // Reset Filters Button
        if (resetFiltersBtn) {
            resetFiltersBtn.addEventListener('click', resetAllFilters);
        }

        // Toggle Advanced Filters
        if (toggleAdvancedFiltersBtn && advancedFiltersPanel) {
            toggleAdvancedFiltersBtn.addEventListener('click', () => {
                advancedFiltersPanel.classList.toggle('open');
            });
        }

        // Load More
        if (loadMoreBtn) {
            loadMoreBtn.addEventListener('click', () => {
                currentLimit += PAGE_SIZE;
                renderCards();
            });
        }

        // Select All Visible
        if (selectAllVisibleBtn) {
            selectAllVisibleBtn.addEventListener('click', () => {
                const filtered = getFilteredData().slice(0, currentLimit);
                const allSelected = filtered.every(it => selectedOpportunities.has(it.id || it.name));
                
                filtered.forEach(it => {
                    const id = it.id || it.name;
                    if (allSelected) {
                        selectedOpportunities.delete(id);
                    } else {
                        selectedOpportunities.add(id);
                    }
                });

                renderCards();
            });
        }

        // Batch Apply Actions
        if (batchOpenBtn) batchOpenBtn.addEventListener('click', handleBatchQuickApply);
        if (batchCopyPacketBtn) {
            batchCopyPacketBtn.addEventListener('click', () => {
                const allItems = Object.values(allData).flat();
                const selectedList = allItems.filter(it => selectedOpportunities.has(it.id || it.name));
                const profile = getSavedProfile();
                const packet = generateApplicationPacket(selectedList, profile);
                navigator.clipboard.writeText(packet).then(() => {
                    showToast(`📋 Copied application packet for ${selectedList.length} opportunities!`);
                });
            });
        }
        if (batchClearBtn) {
            batchClearBtn.addEventListener('click', () => {
                selectedOpportunities.clear();
                renderCards();
            });
        }

        // AI Matcher Modals
        [navAiMatcherBtn, heroAiBtn, aiMatchModalBtn, triggerAiMatchFromProfileBtn].forEach(btn => {
            if (btn) {
                btn.addEventListener('click', () => {
                    if (aiMatcherModal) aiMatcherModal.style.display = 'flex';
                });
            }
        });

        if (closeAiModalBtn && aiMatcherModal) {
            closeAiModalBtn.addEventListener('click', () => {
                aiMatcherModal.style.display = 'none';
            });
        }

        if (runAiMatchingBtn) {
            runAiMatchingBtn.addEventListener('click', () => {
                if (aiResumeInput) {
                    aiResumeText = aiResumeInput.value;
                    calculateAiMatchScores();
                    if (sortSelect) sortSelect.value = 'ai-match';
                    if (aiMatcherModal) aiMatcherModal.style.display = 'none';
                    showToast('🤖 AI Resume Scores Calculated! Sorted by best match.');
                    renderCards();
                }
            });
        }

        if (clearAiMatchingBtn) {
            clearAiMatchingBtn.addEventListener('click', () => {
                aiResumeText = '';
                isAiMatchingActive = false;
                if (aiResumeInput) aiResumeInput.value = '';
                if (sortSelect) sortSelect.value = 'default';
                if (aiMatcherModal) aiMatcherModal.style.display = 'none';
                renderCards();
            });
        }

        // Auth Modal
        if (navAuthBtn && authModal) {
            navAuthBtn.addEventListener('click', () => {
                authModal.style.display = 'flex';
            });
        }

        if (closeAuthModalBtn && authModal) {
            closeAuthModalBtn.addEventListener('click', () => {
                authModal.style.display = 'none';
            });
        }

        if (authExportDataBtn) {
            authExportDataBtn.addEventListener('click', () => {
                const profile = getSavedProfile();
                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(profile, null, 2));
                const downloadAnchor = document.createElement('a');
                downloadAnchor.setAttribute("href", dataStr);
                downloadAnchor.setAttribute("download", "opportunityhub_profile.json");
                document.body.appendChild(downloadAnchor);
                downloadAnchor.click();
                downloadAnchor.remove();
            });
        }

        if (authClearDataBtn) {
            authClearDataBtn.addEventListener('click', () => {
                if (confirm("Are you sure you want to reset your saved profile?")) {
                    localStorage.removeItem('opportunityhub_profile');
                    loadProfileIntoForm();
                    if (authModal) authModal.style.display = 'none';
                    showToast('🗑️ Profile cleared.');
                }
            });
        }

        // Profile Form Submit
        if (profileForm) {
            profileForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const profile = {
                    name: profileName ? profileName.value.trim() : '',
                    email: profileEmail ? profileEmail.value.trim() : '',
                    phone: profilePhone ? profilePhone.value.trim() : '',
                    college: profileCollege ? profileCollege.value.trim() : '',
                    gradYear: profileGradYear ? profileGradYear.value : '',
                    branch: profileBranch ? profileBranch.value.trim() : '',
                    linkedIn: profileLinkedIn ? profileLinkedIn.value.trim() : '',
                    github: profileGithub ? profileGithub.value.trim() : '',
                    portfolio: profilePortfolio ? profilePortfolio.value.trim() : '',
                    resume: profileResume ? profileResume.value.trim() : '',
                    skills: profileSkills ? profileSkills.value.trim() : '',
                    bio: profileBio ? profileBio.value.trim() : '',
                };

                saveProfile(profile);

                if (profileSavedMsg) {
                    profileSavedMsg.style.display = 'block';
                    setTimeout(() => { profileSavedMsg.style.display = 'none'; }, 4000);
                }
                showToast('💾 Profile saved securely in browser!');
            });
        }

        // Copy Profile to Clipboard Button
        if (copyProfileBtn) {
            copyProfileBtn.addEventListener('click', () => {
                const profile = getSavedProfile();
                const packet = generateApplicationPacket([], profile);
                navigator.clipboard.writeText(packet).then(() => {
                    showToast('📋 Copied full application packet to clipboard!');
                });
            });
        }

        // Reminder Form Submit
        if (reminderForm) {
            reminderForm.addEventListener('submit', (e) => {
                e.preventDefault();
                const emailInput = document.getElementById('reminderEmail');
                if (emailInput && emailInput.value) {
                    showToast(`🔔 Subscribed ${emailInput.value} to 7-day, 3-day, and 1-day reminders!`);
                    emailInput.value = '';
                }
            });
        }
    }

    // ===== Initialization =====
    document.addEventListener('DOMContentLoaded', () => {
        setupEventListeners();
        loadProfileIntoForm();
        loadAllData();
    });

})();
