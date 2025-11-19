import { useState, useEffect } from 'react';
import { 
  faXmark, 
  faArrowTrendUp, 
  faCalendar, 
  faUsers, 
  faFileAlt, 
  faCheckCircle, 
  faExclamationCircle, 
  faClock, 
  faBullseye 
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import CircularProgressBar from '../CircularProgressBar';
import { apiGet } from '../../utils/api_utils';


// Progress Status Component
const ProgressStatus = ({ progress }) => {
  const getStatusInfo = (progress) => {
    if (progress >= 90) return { label: 'Excellent', color: 'text-emerald-600', bgColor: 'bg-emerald-100 dark:bg-emerald-900/20', icon: faCheckCircle };
    if (progress >= 70) return { label: 'Good', color: 'text-blue-600', bgColor: 'bg-blue-100 dark:bg-blue-900/20', icon: faArrowTrendUp };
    if (progress >= 50) return { label: 'Fair', color: 'text-yellow-600', bgColor: 'bg-yellow-100 dark:bg-yellow-900/20', icon: faClock };
    if (progress >= 30) return { label: 'Poor', color: 'text-orange-600', bgColor: 'bg-orange-100 dark:bg-orange-900/20', icon: faExclamationCircle };
    return { label: 'Critical', color: 'text-red-600', bgColor: 'bg-red-100 dark:bg-red-900/20', icon: faExclamationCircle };
  };

  const status = getStatusInfo(progress);

  return (
    <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${status.color} ${status.bgColor}`}>
      <FontAwesomeIcon icon={status.icon} className="w-4 h-4 mr-2" />
      {status.label}
    </div>
  );
};

// Metric Card Component
const MetricCard = ({ icon, title, value, description, color = "text-gray-600" }) => {
  return (
    <div className="bg-gray-100 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center justify-between mb-2">
        <FontAwesomeIcon icon={icon} className={`w-6 h-6 ${color}`} />
        <span className="text-2xl font-bold text-gray-800 dark:text-white">{value}</span>
      </div>
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{title}</h3>
      <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
    </div>
  );
};

const AreaDetailModal = ({ 
  area, 
  showModal, 
  onClick,
}) => {
  const [activeTab, setActiveTab] = useState('overview');
  const [deadlines, setDeadlines] = useState([]);
  const [events, setEvents] = useState([]);
  const [areas, setAreas] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch deadlines from backend
  const fetchDeadlines = async () => {
    try {
      setLoading(true);
      const response = await apiGet('/api/deadlines');                
      
      setDeadlines(response.data.deadline || []);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching deadlines:', err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch events from backend
  const fetchEvents = async () => {
    try {
      setLoading(true);
      const response = await apiGet('/api/events');           
      
      setEvents(response.data || []);
    } catch (err) {
      setError(err.message);
      console.error('Error fetching events:', err);
    } finally {
      setLoading(false);
    }
  };

  // Fetch areas from backend
  const fetchAreas = async () => {
    try {
      setLoading(true);
      const response = await apiGet('/api/area');           
      setAreas(response.data.area || []);
      console.log(response.data.area)
    } catch (err) {
      setError(err.message);
      console.error('Error fetching areas:', err);
    } finally {
      setLoading(false);
    }
  };

  // Filter data for current area
  const getAreaData = () => {
    if (!area) return { deadlines: [], events: [] };

    // Ensure arrays exist before filtering
    const safeDeadlines = Array.isArray(deadlines) ? deadlines : [];
    const safeEvents = Array.isArray(events) ? events : [];

    // Filter deadlines for the current area
    // Match by areaID if available, otherwise fallback to name/program matching
    const areaDeadlines = safeDeadlines.filter(deadline => {
      if (!deadline) return false;
      
      // Check if area name matches (considering the backend format "areaNum: areaName")
      const areaNameMatches = deadline.areaName && (
        deadline.areaName.includes(area.areaTitle || area.areaName || '') ||
        deadline.areaName.includes(area.areaNum || '')
      );
      
      // Check if program code matches
      const programMatches = deadline.programCode === area.programCode;
      
      return areaNameMatches || programMatches;
    });

    // Filter events for the current area
    // Events are created from deadlines, so similar filtering logic
    const areaEvents = safeEvents.filter(event => {
      if (!event) return false;
      
      // Check if event title matches area
      const titleMatches = event.title && (
        event.title.includes(area.areaTitle || area.areaName || '') ||
        event.title.includes(area.areaNum || '')
      );
      
      // Check if program color matches (if available)
      const colorMatches = area.programColor && event.color === area.programColor;
      
      return titleMatches || colorMatches;
    });

    return { deadlines: areaDeadlines, events: areaEvents };
  };

  // Calculate deadline priorities based on due date
  const getDeadlinePriority = (dueDate) => {
    const today = new Date();
    // Backend returns date in 'MM-DD-YYYY' format
    const [month, day, year] = dueDate.split('-');
    const due = new Date(year, month - 1, day);
    const diffTime = due - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays < 0) return 'critical'; // Overdue
    if (diffDays <= 3) return 'critical';
    if (diffDays <= 7) return 'high';
    if (diffDays <= 14) return 'medium';
    return 'low';
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'critical': return 'text-red-600 bg-red-100 dark:bg-red-900/20';
      case 'high': return 'text-orange-600 bg-orange-100 dark:bg-orange-900/20';
      case 'medium': return 'text-yellow-600 bg-yellow-100 dark:bg-yellow-900/20';
      case 'low': return 'text-green-600 bg-green-100 dark:bg-green-900/20';
      default: return 'text-gray-600 bg-gray-100 dark:bg-gray-900/20';
    }
  };

  // Helper function to format date for display
  const formatDateForDisplay = (dateString) => {
    const [month, day, year] = dateString.split('-');
    const date = new Date(year, month - 1, day);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  // Helper function to check if deadline is overdue
  const isDeadlineOverdue = (dueDate) => {
    if (!dueDate) return false;
    const today = new Date();
    const [month, day, year] = dueDate.split('-');
    const due = new Date(year, month - 1, day);
    return due < today;
  };

  // Fetch data when modal opens
  useEffect(() => {
    if (showModal && area) {
      fetchDeadlines();
      fetchEvents();
      fetchAreas();
    }
  }, [showModal, area]);

  if (!showModal || !area) return null;

  const { deadlines: areaDeadlines, events: areaEvents } = getAreaData();
  const upcomingDeadlines = Array.isArray(areaDeadlines) ? 
    areaDeadlines.filter(d => d && d.due_date && !isDeadlineOverdue(d.due_date)) : [];
  const overdueDeadlines = Array.isArray(areaDeadlines) ? 
    areaDeadlines.filter(d => d && d.due_date && isDeadlineOverdue(d.due_date)) : [];

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-200 dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-6xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-4">
            <div className="flex-shrink-0">
              <CircularProgressBar strokeColor="stroke-zuccini-500" progress={area.progress || 0} circleWidth="80" placement={''} />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
                {area.areaTitle || area.areaName}
              </h2>
              <p className="text-gray-600 dark:text-gray-300">
                {area.description || `Area ${area.areaNum || ''}`}
              </p>
              <div className="flex items-center space-x-4 mt-2">
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  Program: <span className="font-medium text-gray-700 dark:text-gray-200">
                    {area.programCode}
                  </span>
                </span>
                <ProgressStatus progress={area.progress || 0} />
              </div>
            </div>
          </div>
          <button
            onClick={onClick}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full transition-colors"
          >
            <FontAwesomeIcon icon={faXmark} className="w-6 h-6 text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* Tabs */}
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="flex space-x-8 px-6" aria-label="Tabs">
            {[
              { id: 'overview', name: 'Overview', icon: faArrowTrendUp },
              { id: 'deadlines', name: 'Deadlines', icon: faCalendar },
              { id: 'events', name: 'Events', icon: faClock }
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`${
                  activeTab === tab.id
                    ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center space-x-2`}
              >
                <FontAwesomeIcon icon={tab.icon} className="w-4 h-4" />
                <span>{tab.name}</span>
              </button>
            ))}
          </nav>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[calc(90vh-200px)]">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
              <span className="ml-2 text-gray-600 dark:text-gray-400">Loading...</span>
            </div>
          )}

          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 mb-4">
              <div className="flex items-center">
                <FontAwesomeIcon icon={faExclamationCircle} className="w-5 h-5 text-red-600 mr-2" />
                <span className="text-red-800 dark:text-red-200">Error: {error}</span>
              </div>
            </div>
          )}

          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Metrics Grid */}
              <div className="grid grid-cols-4 gap-4">
                <MetricCard
                  icon={faCalendar}
                  title="Total Deadlines"
                  value={areaDeadlines.length}
                  description="All deadlines for this area"
                  color="text-blue-600"
                />
                <MetricCard
                  icon={faCheckCircle}
                  title="Upcoming"
                  value={upcomingDeadlines.length}
                  description="Upcoming deadlines"
                  color="text-emerald-600"
                />
                <MetricCard
                  icon={faExclamationCircle}
                  title="Overdue"
                  value={overdueDeadlines.length}
                  description="Past due deadlines"
                  color="text-red-600"
                />
                <MetricCard
                  icon={faClock}
                  title="Area Number"
                  value={area.areaNum || 'N/A'}
                  description="Area identifier"
                  color="text-gray-600"
                />
              </div>

              {/* Area Details - Comprehensive */}
              <div className="grid grid-cols-2 gap-4">
                {/* Left Column */}
                <div className="bg-gray-100 inset-shadow-sm inset-shadow-gray-500 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4 pb-3 border-b border-gray-300 dark:border-gray-600">Basic Information</h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Area Number</p>
                      <p className="text-gray-800 dark:text-gray-200 font-semibold">{area.areaNum || '-'}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Area Name (Short)</p>
                      <p className="text-gray-800 dark:text-gray-200">{area.areaTitle || '-'}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Full Name</p>
                      <p className="text-gray-800 dark:text-gray-200">{area.areaName || '-'}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Area ID</p>
                      <p className="text-gray-800 dark:text-gray-200 font-mono text-sm">{area.areaID || '-'}</p>
                    </div>
                  </div>
                </div>

                {/* Right Column */}
                <div className="bg-gray-100 inset-shadow-sm inset-shadow-gray-500 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4 pb-3 border-b border-gray-300 dark:border-gray-600">Program Information</h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Program Code</p>
                      <p className="text-gray-800 dark:text-gray-200 font-semibold">{area.programCode || '-'}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Program ID</p>
                      <p className="text-gray-800 dark:text-gray-200 font-mono text-sm">{area.programID || '-'}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Current Progress</p>
                      <div className="flex items-center space-x-2">
                        <span className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{area.progress || 0}%</span>
                      </div>
                    </div>
                    {area.rating && (
                      <div>
                        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Rating</p>
                        <p className="text-gray-800 dark:text-gray-200">{area.rating.toFixed(2)}</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Subarea & Status Information */}
              <div className="grid grid-cols-2 gap-4">
                {/* Subarea Info */}
                <div className="bg-gray-100 inset-shadow-sm inset-shadow-gray-500 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4 pb-3 border-b border-gray-300 dark:border-gray-600">Subarea Information</h3>
                  <div className="space-y-3">
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Subarea ID</p>
                      <p className="text-gray-800 dark:text-gray-200">{area.subareaID || '-'}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Subarea Name</p>
                      <p className="text-gray-800 dark:text-gray-200">{area.subareaName || 'Not assigned'}</p>
                    </div>
                  </div>
                </div>

                {/* Status & Archive Info */}
                <div className="bg-gray-100 inset-shadow-sm inset-shadow-gray-500 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4 pb-3 border-b border-gray-300 dark:border-gray-600">Status</h3>
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Archived</p>
                      <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                        area.archived 
                          ? 'bg-red-100 dark:bg-red-900/20 text-red-700 dark:text-red-400' 
                          : 'bg-emerald-100 dark:bg-emerald-900/20 text-emerald-700 dark:text-emerald-400'
                      }`}>
                        {area.archived ? 'Archived' : 'Active'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">Status</p>
                      <ProgressStatus progress={area.progress || 0} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Template & Reference Info */}
              <div className="bg-gray-100 inset-shadow-sm inset-shadow-gray-500 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4 pb-3 border-b border-gray-300 dark:border-gray-600">Technical Information</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Template ID</p>
                    <p className="text-gray-800 dark:text-gray-200 font-mono text-sm">{area.templateID || '-'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Applied Template ID</p>
                    <p className="text-gray-800 dark:text-gray-200 font-mono text-sm">{area.appliedTemplateID || '-'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Area Blueprint ID</p>
                    <p className="text-gray-800 dark:text-gray-200 font-mono text-sm">{area.areaBlueprintID || '-'}</p>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Institute ID</p>
                    <p className="text-gray-800 dark:text-gray-200 font-mono text-sm">{area.instID || '-'}</p>
                  </div>
                </div>
              </div>

              {/* Quick Stats */}
              <div className="bg-gray-100 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">Quick Stats</h3>
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Completion Rate</span>
                    <span className="text-sm font-medium text-gray-800 dark:text-gray-200">{area.progress || 0}%</span>
                  </div>
                  <div className="w-full bg-gray-300 dark:bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-emerald-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${area.progress || 0}%` }}
                    ></div>
                  </div>
                  
                  <div className="flex items-center justify-between pt-2">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Total Deadlines</span>
                    <span className="text-sm font-medium text-blue-600 dark:text-blue-400">
                      {areaDeadlines.length}
                    </span>
                  </div>
                  
                  {upcomingDeadlines.length > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Upcoming Deadlines</span>
                      <span className="text-sm font-medium text-blue-600 dark:text-blue-400">
                        {upcomingDeadlines.length}
                      </span>
                    </div>
                  )}
                  
                  {overdueDeadlines.length > 0 && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-600 dark:text-gray-400">Overdue Items</span>
                      <span className="text-sm font-medium text-red-600 dark:text-red-400">
                        {overdueDeadlines.length}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'deadlines' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white">Area Deadlines</h3>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {areaDeadlines.length} total deadlines
                </span>
              </div>
              
              {areaDeadlines.length === 0 ? (
                <div className="text-center py-8">
                    {console.log(`Area Deadlines: ${areaDeadlines}`)}
                  <FontAwesomeIcon icon={faCalendar} className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-4" />
                  <p className="text-gray-500 dark:text-gray-400">No deadlines found for this area</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {areaDeadlines
                    .sort((a, b) => {
                      // Sort by due date
                      const [monthA, dayA, yearA] = a.due_date.split('-');
                      const [monthB, dayB, yearB] = b.due_date.split('-');
                      const dateA = new Date(yearA, monthA - 1, dayA);
                      const dateB = new Date(yearB, monthB - 1, dayB);
                      return dateA - dateB;
                    })
                    .map((deadline) => {
                      const priority = getDeadlinePriority(deadline.due_date);
                      const isOverdue = isDeadlineOverdue(deadline.due_date);
                      
                      return (
                        <div
                          key={deadline.deadlineID}
                          className={`bg-gray-100 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 border rounded-lg p-4 ${
                            isOverdue ? 'border-red-200 dark:border-red-800' : 'border-gray-200 dark:border-gray-700'
                          }`}
                        >
                          <div className="flex items-start justify-between">
                            <div className="flex-1">
                              <div className="flex items-center space-x-2 mb-2">
                                <h4 className="font-medium text-gray-800 dark:text-white">
                                  {deadline.areaName}
                                </h4>
                                {isOverdue && (
                                  <span className="px-2 py-1 bg-red-100 dark:bg-red-900/20 text-red-600 text-xs rounded-full">
                                    Overdue
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                                {deadline.content}
                              </p>
                              <div className="flex items-center space-x-4 text-sm text-gray-500 dark:text-gray-400">
                                <div className="flex items-center space-x-1">
                                  <FontAwesomeIcon icon={faCalendar} className="w-4 h-4" />
                                  <span>Due: {formatDateForDisplay(deadline.due_date)}</span>
                                </div>
                                <span>Program: {deadline.programCode}</span>
                                <span>{deadline.programName}</span>
                              </div>
                            </div>
                            <div className="flex flex-col items-end space-y-2">
                              <span className={`px-2 py-1 rounded-full text-xs font-medium capitalize ${getPriorityColor(priority)}`}>
                                {priority}
                              </span>
                              {deadline.programColor && (
                                <div
                                  className="w-4 h-4 rounded-full border-2 border-white dark:border-gray-800"
                                  style={{ backgroundColor: deadline.programColor }}
                                  title={`${deadline.programName} Program`}
                                ></div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          )}

          {activeTab === 'events' && (
            <div className="space-y-4">
                {console.log(`Area Events: ${areaEvents}`)}
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-gray-800 dark:text-white">Area Events</h3>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {areaEvents.length} events
                </span>
              </div>
              
              {areaEvents.length === 0 ? (
                <div className="text-center py-8">
                  <FontAwesomeIcon icon={faClock} className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-4" />
                  <p className="text-gray-500 dark:text-gray-400">No events found for this area</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {areaEvents
                    .sort((a, b) => new Date(a.start) - new Date(b.start))
                    .map((event) => (
                      <div
                        key={event.id}
                        className="bg-gray-100 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4"
                      >
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h4 className="font-medium text-gray-800 dark:text-white mb-2">
                              {event.title}
                            </h4>
                            {event.content && (
                              <p className="text-sm text-gray-600 dark:text-gray-300 mb-2">
                                {event.content}
                              </p>
                            )}
                            <div className="flex items-center space-x-2 text-sm text-gray-500 dark:text-gray-400">
                              <FontAwesomeIcon icon={faCalendar} className="w-4 h-4" />
                              <span>{new Date(event.start).toLocaleDateString('en-US', {
                                year: 'numeric',
                                month: 'long',
                                day: 'numeric'
                              })}</span>
                            </div>
                          </div>
                          {event.color && (
                            <div
                              className="w-6 h-6 rounded-full border-2 border-white dark:border-gray-800 flex-shrink-0"
                              style={{ backgroundColor: event.color }}
                            ></div>
                          )}
                        </div>
                      </div>
                    ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default AreaDetailModal;