/**
 * OpportunityHub — Main Application Script
 * Loads JSON data, renders opportunity cards, handles comprehensive filtering,
 * profile management, and reminder subscriptions.
 */

(function () {
    'use strict';

    // ===== Configuration =====
    const DATA_BASE_PATH = '../data';
    const CATEGORIES = [
        { key: 'hackathons', file: 'hackathons.json', icon: '🏆' },
        { key: 'internships', file: 'internships.json', icon: '💼' },
        { key: 'competitions', file: 'competitions.json', icon: '⚔️' },
        { key: 'open-source-programs', file: 'open-source-programs.json', icon: '🌍' },
        { key: 'fellowships', file: 'fellowships.json', icon: '🎓' },
    ];

    // ===== State =====
    let allData = {};
    let activeCategory = 'hackathons';
    let currentLimit = 36;
    const PAGE_SIZE = 36;
    let activeChips = new Set();

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
    
    // Comprehensive Filters
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
    
    // General
    const tabs = document.querySelectorAll('.tab');
    const toast = document.getElementById('toast');
    const navbar = document.getElementById('navbar');
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');

    // ===== Data Loading =====
    async function loadAllData() {
        const promises = CATEGORIES.map(async (cat) => {
            try {
                const res = await fetch(`${DATA_BASE_PATH}/${cat.file}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                allData[cat.key] = await res.json();
            } catch (err) {
                console.warn(`Failed to load ${cat.file}:`, err);
                allData[cat.key] = [];
            }
        });
        await Promise.all(promises);
        updateStats();
        renderCards();
    }

    // ===== Stats =====
    function updateStats() {
        animateCounter('stat-hackathons', allData['hackathons']?.length || 0);
        animateCounter('stat-internships', allData['internships']?.length || 0);
        animateCounter('stat-competitions', allData['competitions']?.length || 0);
        animateCounter('stat-programs', allData['open-source-programs']?.length || 0);
        animateCounter('stat-fellowships', allData['fellowships']?.length || 0);
    }

    function animateCounter(elementId, target) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const numberEl = el.querySelector('.stat-number');
        const duration = 1200;
        const startTime = performance.now();

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            numberEl.textContent = Math.round(eased * target);
            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }
        requestAnimationFrame(update);
    }

    // ===== Card Rendering =====
    function renderCards(append = false) {
        const items = allData[activeCategory] || [];
        const filtered = applyFilters(items);
        const sorted = applySorting(filtered);

        if (!append) {
            cardsGrid.innerHTML = '';
            currentLimit = PAGE_SIZE;
        }

        const visibleItems = sorted.slice(0, currentLimit);
        emptyState.style.display = sorted.length === 0 ? 'block' : 'none';

        if (resultsCount) {
            resultsCount.innerHTML = sorted.length > 0
                ? `Showing <strong>${Math.min(visibleItems.length, sorted.length)}</strong> of <strong>${sorted.length.toLocaleString()}</strong> opportunities`
                : 'No opportunities match your selected filters';
        }

        // Render current batch
        const fragment = document.createDocumentFragment();
        const startIdx = append ? (currentLimit - PAGE_SIZE) : 0;
        
        sorted.slice(startIdx, currentLimit).forEach((item, index) => {
            const card = createCard(item, index);
            fragment.appendChild(card);
        });
        cardsGrid.appendChild(fragment);

        // Manage Load More button
        if (loadMoreContainer) {
            if (visibleItems.length < sorted.length) {
                loadMoreContainer.style.display = 'block';
                if (loadMoreBtn) {
                    loadMoreBtn.textContent = `Load More (${sorted.length - visibleItems.length} remaining) ⬇️`;
                }
            } else {
                loadMoreContainer.style.display = 'none';
            }
        }

        // Update active filter badge & reset button visibility
        updateFilterBadge();
    }

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener('click', () => {
            currentLimit += PAGE_SIZE;
            renderCards(true);
        });
    }

    function createCard(item, index) {
        const card = document.createElement('div');
        card.className = 'opportunity-card';
        card.style.animationDelay = `${(index % 20) * 0.03}s`;

        const statusClass = item.status || 'open';
        const statusLabel = {
            'open': 'Open',
            'closed': 'Closed',
            'coming-soon': 'Coming Soon'
        }[statusClass] || statusClass;

        // Build detail chips
        let details = [];
        if (item.deadline) details.push({ icon: '📅', text: formatDate(item.deadline) });
        if (item.stipend) details.push({ icon: '💰', text: item.stipend });
        else if (item.fee) details.push({ icon: '💵', text: item.fee });
        if (item.prize) details.push({ icon: '🏆', text: item.prize });
        if (item.mode) details.push({ icon: '📍', text: item.mode });
        if (item.location && item.location !== item.mode) details.push({ icon: '🌏', text: item.location });
        if (item.duration) details.push({ icon: '⏱️', text: item.duration });
        if (item.eligibility) details.push({ icon: '👤', text: truncate(item.eligibility, 38) });

        const detailsHTML = details.map(d =>
            `<span class="card-detail"><span class="card-detail-icon">${d.icon}</span>${escapeHTML(d.text)}</span>`
        ).join('');

        card.innerHTML = `
            <div class="card-header">
                <h3 class="card-title">${escapeHTML(item.name)}</h3>
                <span class="card-status ${statusClass}">${statusLabel}</span>
            </div>
            <div class="card-organizer">${escapeHTML(item.organizer)}</div>
            <p class="card-description">${escapeHTML(item.description)}</p>
            <div class="card-details">${detailsHTML}</div>
            <div class="card-actions">
                <a href="${escapeHTML(item.applicationLink || item.website || '#')}" target="_blank" rel="noopener" class="btn btn-apply">Apply →</a>
                <button class="btn btn-quick-apply" onclick="quickApply('${escapeHTML(item.applicationLink || item.website || '')}', '${escapeHTML(item.name)}')">⚡ Quick Apply</button>
            </div>
        `;

        return card;
    }

    // ===== Comprehensive Filtering Engine =====
    function applyFilters(items) {
        const search = (searchInput?.value || '').toLowerCase().trim();
        const domain = domainFilter?.value || 'all';
        const location = locationFilter?.value || 'all';
        const type = typeFilter?.value || 'all';
        const status = statusFilter?.value || 'all';
        const stipend = stipendFilter?.value || 'all';
        const mode = modeFilter?.value || 'all';

        return items.filter(item => {
            const nameLower = (item.name || '').toLowerCase();
            const descLower = (item.description || '').toLowerCase();
            const orgLower = (item.organizer || '').toLowerCase();
            const locLower = (item.location || item.mode || '').toLowerCase();
            const eligLower = (item.eligibility || '').toLowerCase();
            const stipLower = (item.stipend || item.fee || item.prize || '').toLowerCase();
            const tagsLower = (item.tags || []).join(' ').toLowerCase();
            const fullText = [nameLower, descLower, orgLower, locLower, eligLower, stipLower, tagsLower].join(' ');

            // 1. Text Search (Name, Company, Skills, Location, etc.)
            if (search) {
                const searchTokens = search.split(/\s+/);
                const matchesAllTokens = searchTokens.every(tok => fullText.includes(tok));
                if (!matchesAllTokens) return false;
            }

            // 2. Domain / Role Filter
            if (domain !== 'all') {
                if (domain === 'swe') {
                    const isSwe = /software|full\s*stack|backend|frontend|web|developer|swe|engineering|programmer|dev/i.test(nameLower + ' ' + descLower);
                    if (!isSwe) return false;
                } else if (domain === 'ai-ml') {
                    const isAi = /ai|artificial\s*intelligence|machine\s*learning|deep\s*learning|llm|neural|computer\s*vision|nlp|pytorch|tensorflow/i.test(fullText);
                    if (!isAi) return false;
                } else if (domain === 'data') {
                    const isData = /data\s*science|data\s*analyst|data\s*engineer|analytics|business\s*intelligence|bi\b|sql|statistics/i.test(fullText);
                    if (!isData) return false;
                } else if (domain === 'cloud') {
                    const isCloud = /cloud|devops|sre|site\s*reliability|infrastructure|aws|azure|gcp|kubernetes|docker|terraform/i.test(fullText);
                    if (!isCloud) return false;
                } else if (domain === 'security') {
                    const isSec = /security|infosec|cyber|penetration|vulnerability|cryptography|threat|soc\b/i.test(fullText);
                    if (!isSec) return false;
                } else if (domain === 'mobile') {
                    const isMob = /mobile|android|ios|flutter|react\s*native|swift|kotlin/i.test(fullText);
                    if (!isMob) return false;
                } else if (domain === 'hardware') {
                    const isHw = /hardware|embedded|firmware|fpga|asic|vhdl|verilog|electrical|robotics|microcontroller/i.test(fullText);
                    if (!isHw) return false;
                } else if (domain === 'quant') {
                    const isQuant = /quant|quantitative|trading|algorithmic|hedge|financial\s*engineer/i.test(fullText);
                    if (!isQuant) return false;
                } else if (domain === 'pm-design') {
                    const isPm = /product\s*manager|product\s*management|ui|ux|design|product\s*design/i.test(fullText);
                    if (!isPm) return false;
                }
            }

            // 3. Location / Region Filter
            if (location !== 'all') {
                if (location === 'remote') {
                    const isRemote = /remote|work\s*from\s*home|wfh|online|virtual/i.test(locLower + ' ' + (item.mode || ''));
                    if (!isRemote) return false;
                } else if (location === 'india') {
                    const isIndia = /india|bangalore|bengaluru|hyderabad|pune|mumbai|delhi|noida|gurgaon|gurugram|chennai|kolkata|ahmedabad|kerala|iit|isro/i.test(fullText);
                    if (!isIndia) return false;
                } else if (location === 'usa') {
                    const isUsa = /united\s*states|usa|\bus\b|california|\bca\b|new\s*york|\bny\b|texas|\btx\b|seattle|\bwa\b|boston|\bma\b|austin|sf|san\s*francisco/i.test(locLower);
                    if (!isUsa) return false;
                } else if (location === 'canada') {
                    const isCanada = /canada|toronto|vancouver|waterloo|montreal|ontario|quebec|mitacs/i.test(fullText);
                    if (!isCanada) return false;
                } else if (location === 'europe') {
                    const isEurope = /europe|uk|united\s*kingdom|london|germany|berlin|munich|netherlands|amsterdam|france|paris|switzerland|zurich/i.test(fullText);
                    if (!isEurope) return false;
                } else if (location === 'international') {
                    const isIntl = /global|worldwide|international|remote/i.test(fullText);
                    if (!isIntl) return false;
                }
            }

            // 4. Level & Type Filter
            if (type !== 'all') {
                if (type === 'summer') {
                    const isSummer = /summer|2025|2026|2027/i.test(fullText);
                    if (!isSummer) return false;
                } else if (type === 'newgrad') {
                    const isNewGrad = /new\s*grad|new\s*college\s*grad|entry\s*level|graduate|early\s*career/i.test(fullText);
                    if (!isNewGrad) return false;
                } else if (type === 'offseason') {
                    const isOffSeason = /off-season|fall|spring|winter|co-op/i.test(fullText);
                    if (!isOffSeason) return false;
                } else if (type === 'research') {
                    const isResearch = /research|fellowship|mitacs|isro|lab|academic|university/i.test(fullText);
                    if (!isResearch) return false;
                } else if (type === 'opensource') {
                    const isOSS = /open\s*source|gsoc|lfx|outreachy|github\s*externship|foss/i.test(fullText);
                    if (!isOSS) return false;
                }
            }

            // 5. Status Filter
            if (status !== 'all') {
                if (item.status !== status) return false;
            }

            // 6. Stipend & Fee Filter
            if (stipend !== 'all') {
                if (stipend === 'paid') {
                    const isPaid = (item.stipend && !/unpaid|none/i.test(item.stipend)) ||
                                   /\$|₹|stipend|competitive|salary|cad|eur|month|year/i.test(stipLower);
                    if (!isPaid) return false;
                } else if (stipend === 'free') {
                    const isFree = /free/i.test(item.fee || '') || (item.stipend && !item.fee);
                    if (!isFree) return false;
                } else if (stipend === 'prizes') {
                    const hasPrizes = /prize|award|grant|cash|\$|₹/i.test(item.prize || '') || /awards|rewards/i.test(stipLower);
                    if (!hasPrizes) return false;
                }
            }

            // 7. Mode Filter
            if (mode !== 'all') {
                const itemMode = (item.mode || '').toLowerCase();
                if (mode === 'online' && !(/online|remote|virtual|wfh/i.test(itemMode))) return false;
                if (mode === 'in-person' && !(/in-person|onsite|offline/i.test(itemMode))) return false;
                if (mode === 'hybrid' && !(/hybrid/i.test(itemMode))) return false;
            }

            // 8. Quick Chips Filters
            for (const chip of activeChips) {
                if (chip === 'remote' && !/remote|wfh|online|virtual/i.test(locLower + ' ' + (item.mode || ''))) return false;
                if (chip === 'india' && !/india|bangalore|bengaluru|hyderabad|pune|mumbai|delhi|noida|gurgaon|chennai|kolkata|isro/i.test(fullText)) return false;
                if (chip === 'faang' && !/google|microsoft|amazon|meta|apple|netflix|nvidia|uber|salesforce|spacex|adobe/i.test(orgLower + ' ' + nameLower)) return false;
                if (chip === 'ai-ml' && !/ai|machine\s*learning|deep\s*learning|llm|data\s*science/i.test(fullText)) return false;
                if (chip === 'newgrad' && !/new\s*grad|new\s*college\s*grad|entry\s*level|early\s*career/i.test(fullText)) return false;
                if (chip === 'summer' && !/summer|2025|2026|2027/i.test(fullText)) return false;
                if (chip === 'paid' && !(/\$|₹|stipend|competitive|salary|cad|eur/i.test(stipLower))) return false;
                if (chip === 'open' && item.status !== 'open') return false;
            }

            return true;
        });
    }

    // ===== Sorting Engine =====
    function applySorting(items) {
        const sortBy = sortSelect?.value || 'default';
        const sorted = [...items];

        if (sortBy === 'deadline') {
            sorted.sort((a, b) => {
                const dateA = a.deadline ? new Date(a.deadline).getTime() : Infinity;
                const dateB = b.deadline ? new Date(b.deadline).getTime() : Infinity;
                return (isNaN(dateA) ? Infinity : dateA) - (isNaN(dateB) ? Infinity : dateB);
            });
        } else if (sortBy === 'company-asc') {
            sorted.sort((a, b) => (a.organizer || a.name || '').localeCompare(b.organizer || b.name || ''));
        } else if (sortBy === 'company-desc') {
            sorted.sort((a, b) => (b.organizer || b.name || '').localeCompare(a.organizer || a.name || ''));
        }

        return sorted;
    }

    // ===== Filter Badge & Reset Manager =====
    function updateFilterBadge() {
        let count = 0;
        if (searchInput?.value.trim()) count++;
        if (domainFilter?.value !== 'all') count++;
        if (locationFilter?.value !== 'all') count++;
        if (typeFilter?.value !== 'all') count++;
        if (statusFilter?.value !== 'all') count++;
        if (stipendFilter?.value !== 'all') count++;
        if (modeFilter?.value !== 'all') count++;
        count += activeChips.size;

        if (activeFilterBadge) {
            if (count > 0) {
                activeFilterBadge.textContent = count;
                activeFilterBadge.style.display = 'inline-flex';
            } else {
                activeFilterBadge.style.display = 'none';
            }
        }

        if (resetFiltersBtn) {
            resetFiltersBtn.style.display = count > 0 ? 'inline-block' : 'none';
        }

        if (searchClearBtn) {
            searchClearBtn.style.display = searchInput?.value ? 'flex' : 'none';
        }
    }

    function resetAllFilters() {
        if (searchInput) searchInput.value = '';
        if (domainFilter) domainFilter.value = 'all';
        if (locationFilter) locationFilter.value = 'all';
        if (typeFilter) typeFilter.value = 'all';
        if (statusFilter) statusFilter.value = 'all';
        if (stipendFilter) stipendFilter.value = 'all';
        if (modeFilter) modeFilter.value = 'all';
        if (sortSelect) sortSelect.value = 'default';
        
        activeChips.clear();
        quickChips.forEach(chip => chip.classList.remove('active'));

        renderCards();
    }

    // ===== Quick Apply =====
    window.quickApply = function (link, name) {
        const profile = JSON.parse(localStorage.getItem('opportunityhub_profile') || '{}');

        if (!profile.name) {
            showToast('⚠️ Save your profile first in the Quick Apply section!');
            document.getElementById('quick-apply').scrollIntoView({ behavior: 'smooth' });
            return;
        }

        // Copy profile to clipboard
        const profileText = [
            `Name: ${profile.name}`,
            `Email: ${profile.email}`,
            `College: ${profile.college}`,
            `Year: ${profile.year}`,
            `Branch: ${profile.branch}`,
            `Skills: ${profile.skills}`,
            profile.resume ? `Resume: ${profile.resume}` : ''
        ].filter(Boolean).join('\n');

        navigator.clipboard.writeText(profileText).then(() => {
            showToast(`📋 Profile copied! Opening ${name}...`);
            setTimeout(() => {
                if (link && link !== '#') window.open(link, '_blank');
            }, 500);
        }).catch(() => {
            showToast('Opening application page...');
            if (link && link !== '#') window.open(link, '_blank');
        });

        // Track applied
        const applied = JSON.parse(localStorage.getItem('opportunityhub_applied') || '[]');
        if (!applied.includes(name)) {
            applied.push(name);
            localStorage.setItem('opportunityhub_applied', JSON.stringify(applied));
        }
    };

    // ===== Profile Form =====
    function initProfile() {
        const form = document.getElementById('profileForm');
        if (!form) return;

        // Load saved
        const saved = JSON.parse(localStorage.getItem('opportunityhub_profile') || '{}');
        if (saved.name) document.getElementById('profileName').value = saved.name;
        if (saved.email) document.getElementById('profileEmail').value = saved.email;
        if (saved.college) document.getElementById('profileCollege').value = saved.college;
        if (saved.year) document.getElementById('profileYear').value = saved.year;
        if (saved.branch) document.getElementById('profileBranch').value = saved.branch;
        if (saved.skills) document.getElementById('profileSkills').value = saved.skills;
        if (saved.resume) document.getElementById('profileResume').value = saved.resume;

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const profile = {
                name: document.getElementById('profileName').value,
                email: document.getElementById('profileEmail').value,
                college: document.getElementById('profileCollege').value,
                year: document.getElementById('profileYear').value,
                branch: document.getElementById('profileBranch').value,
                skills: document.getElementById('profileSkills').value,
                resume: document.getElementById('profileResume').value,
            };
            localStorage.setItem('opportunityhub_profile', JSON.stringify(profile));
            showToast('💾 Profile saved! Ready for 1-click apply.');
        });

        document.getElementById('copyProfileBtn')?.addEventListener('click', function () {
            const profile = JSON.parse(localStorage.getItem('opportunityhub_profile') || '{}');
            if (!profile.name) {
                showToast('⚠️ Fill and save your profile first!');
                return;
            }
            const text = [
                `Name: ${profile.name}`,
                `Email: ${profile.email}`,
                `College: ${profile.college}`,
                `Year: ${profile.year}`,
                `Branch: ${profile.branch}`,
                `Skills: ${profile.skills}`,
                profile.resume ? `Resume: ${profile.resume}` : ''
            ].filter(Boolean).join('\n');

            navigator.clipboard.writeText(text).then(() => {
                showToast('📋 Profile copied to clipboard!');
            });
        });
    }

    // ===== Reminder Form =====
    function initReminders() {
        const form = document.getElementById('reminderForm');
        if (!form) return;

        form.addEventListener('submit', function (e) {
            e.preventDefault();
            const email = document.getElementById('reminderEmail').value;
            const categories = Array.from(
                form.querySelectorAll('input[type="checkbox"]:checked')
            ).map(cb => cb.value);

            const subscription = { email, categories, subscribedAt: new Date().toISOString() };

            const subs = JSON.parse(localStorage.getItem('opportunityhub_reminders') || '[]');
            subs.push(subscription);
            localStorage.setItem('opportunityhub_reminders', JSON.stringify(subs));

            showToast('🔔 Subscribed! You\'ll receive deadline reminders.');
            form.reset();
        });
    }

    // ===== Navigation =====
    function initNav() {
        window.addEventListener('scroll', function () {
            navbar.classList.toggle('scrolled', window.scrollY > 50);
        });

        navToggle.addEventListener('click', function () {
            navLinks.classList.toggle('open');
        });

        navLinks.querySelectorAll('a').forEach(link => {
            link.addEventListener('click', () => {
                navLinks.classList.remove('open');
            });
        });
    }

    // ===== Tabs =====
    function initTabs() {
        tabs.forEach(tab => {
            tab.addEventListener('click', function () {
                tabs.forEach(t => t.classList.remove('active'));
                this.classList.add('active');
                activeCategory = this.dataset.category;
                renderCards();
            });
        });
    }

    // ===== Filter Listeners =====
    function initFilters() {
        // Text Search
        let debounceTimer;
        searchInput?.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => renderCards(), 150);
        });

        searchClearBtn?.addEventListener('click', () => {
            searchInput.value = '';
            renderCards();
        });

        // Dropdowns
        sortSelect?.addEventListener('change', () => renderCards());
        domainFilter?.addEventListener('change', () => renderCards());
        locationFilter?.addEventListener('change', () => renderCards());
        typeFilter?.addEventListener('change', () => renderCards());
        statusFilter?.addEventListener('change', () => renderCards());
        stipendFilter?.addEventListener('change', () => renderCards());
        modeFilter?.addEventListener('change', () => renderCards());

        // Quick Chips
        quickChips.forEach(chip => {
            chip.addEventListener('click', function () {
                const chipKey = this.dataset.chip;
                if (activeChips.has(chipKey)) {
                    activeChips.delete(chipKey);
                    this.classList.remove('active');
                } else {
                    activeChips.add(chipKey);
                    this.classList.add('active');
                }
                renderCards();
            });
        });

        // Toggle Advanced Panel
        toggleAdvancedFiltersBtn?.addEventListener('click', function () {
            if (advancedFiltersPanel) {
                const isHidden = advancedFiltersPanel.style.display === 'none';
                advancedFiltersPanel.style.display = isHidden ? 'grid' : 'none';
                this.classList.toggle('active', isHidden);
            }
        });

        // Reset Button
        resetFiltersBtn?.addEventListener('click', resetAllFilters);
    }

    // ===== Scroll Animations =====
    function initScrollAnimations() {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                }
            });
        }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });

        document.querySelectorAll(
            '.section-header, .profile-card, .reminder-card, .reference-card, .stats-container'
        ).forEach(el => {
            el.classList.add('animate-on-scroll');
            observer.observe(el);
        });
    }

    // ===== Helpers =====
    function formatDate(dateStr) {
        if (!dateStr || dateStr.toLowerCase().includes('rolling') || dateStr.toLowerCase().includes('various') || dateStr.toLowerCase().includes('check')) {
            return dateStr;
        }
        try {
            const date = new Date(dateStr);
            if (isNaN(date.getTime())) return dateStr;
            return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch {
            return dateStr;
        }
    }

    function truncate(str, maxLen) {
        if (!str) return '';
        return str.length > maxLen ? str.substring(0, maxLen) + '…' : str;
    }

    function escapeHTML(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function showToast(message) {
        toast.textContent = message;
        toast.classList.remove('show');
        void toast.offsetWidth;
        toast.classList.add('show');
        setTimeout(() => toast.classList.remove('show'), 3200);
    }

    // ===== Init =====
    document.addEventListener('DOMContentLoaded', function () {
        initNav();
        initTabs();
        initFilters();
        initProfile();
        initReminders();
        loadAllData();
        initScrollAnimations();
    });
})();
