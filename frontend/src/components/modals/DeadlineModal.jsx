import {
    faCircleXmark,
    faBookOpen,
    faCalendar,
    faClock,
    faBook
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';

const DeadlineModal = ({id, programName, programCode, area, criteria, date, color = "#3B82F6", content, onClick, showModal}) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center  justify-center bg-black/50 backdrop-blur-sm">
      <div className={`relative overflow-y-scroll bg-gray-200 dark:bg-gray-900 rounded-2xl shadow-2xl max-w-5xl w-full mx-4 max-h-[90vh] overflow-hidden ${showModal ? 'fade-in' : 'fade-out'}`}>
        {/* Header with accent color */}
        <div 
          className="w-full h-2"
          style={{ backgroundColor: color }}
        />
        
        {/* Close button */}
        <FontAwesomeIcon 
        icon={faCircleXmark} 
        className="absolute p-2 text-gray-400 transition-all duration-200 rounded-full top-4 right-4 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800" 
        onClick={onClick} 
    />

        <div className="p-8">
          {/* Program Title */}
          <div className="mb-8">
            <h1 className="mb-2 text-3xl font-bold text-gray-900 dark:text-white">
              {programName}
            </h1>
            <div className="flex items-center space-x-2">
              <span 
                className="px-3 py-1 text-sm font-medium text-white rounded-full"
                style={{ backgroundColor: color }}
              >
                {programCode}
              </span>
            </div>
          </div>

          {/* Info Grid */}
          <div className="grid gap-6 mb-8 md:grid-cols-2">
            {/* Area */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2 text-gray-600 dark:text-gray-400">
                <FontAwesomeIcon icon={faBookOpen} />
                <span className="font-medium">Area</span>
              </div>
              <p className="pl-6 text-lg text-gray-900 dark:text-white">
                {area}
              </p>
            </div>

            {/* Deadline */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2 text-gray-600 dark:text-gray-400">
                <FontAwesomeIcon icon={faBook} />
                <span className="font-medium">Criteria</span>
              </div>
              {Array.isArray(criteria) && criteria.length > 0 ? (
                <div className="pl-6 flex flex-wrap gap-2">
                  {criteria.map((crit) => (
                    <span
                      key={crit.criteriaID}
                      className="px-3 py-1 text-xs font-medium rounded-full bg-emerald-200 text-emerald-600 dark:bg-emerald-800 dark:text-emerald-50"
                    >
                      {crit.criteriaID}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="pl-6 text-gray-500 dark:text-gray-400 text-sm">
                  No criteria found for this deadline.
                </p>
              )}              
            </div>

             {/* Deadline */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2 text-gray-600 dark:text-gray-400">
                <FontAwesomeIcon icon={faCalendar} />
                <span className="font-medium">Deadline</span>
              </div>
              <p className="pl-6 text-lg font-semibold text-gray-900 dark:text-white">
                {date}
              </p>
            </div>        
          </div>

          {/* Description */}
          <div className="space-y-4">
            <div className="flex items-center space-x-2 text-gray-600 dark:text-gray-400">
              <FontAwesomeIcon icon={faClock} />
              <span className="font-medium">Description</span>
            </div>
            <div className="bg-gray-100 dark:bg-gray-800 rounded-xl p-6 min-h-[120px]">
              <div className="leading-relaxed text-gray-700 whitespace-pre-line dark:text-gray-300">
                {content || "No description provided."}
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="pt-6 mt-2 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500 dark:text-gray-400">
                Deadline ID: {id}
              </span>
              <button
                onClick={onClick}
                className="px-6 py-2 font-medium text-gray-700 transition-colors duration-200 bg-gray-100 rounded-lg hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-300"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DeadlineModal;