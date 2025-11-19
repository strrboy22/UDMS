import { useState, useEffect } from 'react'
import {faSearch, faFilter, faCalendar, faRectangleList, faLayerGroup, faChartPie, faBookOpen, faArrowTrendUp} from '@fortawesome/free-solid-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { apiGet } from '../utils/api_utils'
import { adminHelper } from '../utils/auth_utils'
import StatusModal from '../components/modals/StatusModal'
import {Area} from './Dashboard'
import AreaDetailModal from '../components/modals/AreaDetailModal'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LabelList } from 'recharts'
import CircularProgressBar from '../components/CircularProgressBar'

// Filter Component
const FilterPanel = ({ filters, onFilterChange, programs = [] }) => {
  return (
    <div className="flex flex-wrap gap-4 p-4 bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      {/* Program Filter */}
      <div className="flex flex-col">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Program</label>
        <select value={filters.program} onChange={(e) => onFilterChange('program', e.target.value)} className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-900 text-gray-700 dark:text-white focus:ring-2 focus:ring-emerald-500 focus:border-transparent" >
          <option value="">All Departments</option>
          {programs.map(program => (
            <option key={program.code} value={program.code}>{program.name}</option>
          ))}
        </select>
      </div>

      {/* Progress Filter */}
      <div className="flex flex-col">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Progress Level</label>
        <select value={filters.progressLevel} onChange={(e) => onFilterChange('progressLevel', e.target.value)} className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-900 text-gray-700 dark:text-white focus:ring-2 focus:ring-emerald-500 focus:border-transparent" >
          <option value="">All Levels</option>
          <option value="excellent">Excellent (80%+)</option>
          <option value="good">Good (60-79%)</option>
          <option value="fair">Fair (40-59%)</option>
          <option value="needs-attention">Needs Attention ( Less than 40%)</option>
        </select>
      </div>

      {/* Sort */}
      <div className="flex flex-col">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Sort By</label>
        <select value={filters.sortBy} onChange={(e) => onFilterChange('sortBy', e.target.value)} className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-900 text-gray-700 dark:text-white focus:ring-2 focus:ring-emerald-500 focus:border-transparent" >
          <option value="name">Area Name</option>
          <option value="progress-high">Progress (High to Low)</option>
          <option value="progress-low">Progress (Low to High)</option>
          <option value="updated">Last Updated</option>
        </select>
      </div>
    </div>
  )
}

// Statistics Panel Component
const StatsPanel = ({ areas }) => {
  const totalAreas = areas.length
  const avgProgress = Math.round(areas.reduce((sum, area) => sum + area.progress, 0) / totalAreas)
  const excellentAreas = areas.filter(area => area.progress >= 80).length
  const needsAttentionAreas = areas.filter(area => area.progress < 40).length

  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Total Areas</p>
            <p className="text-2xl font-bold text-gray-800 dark:text-white">{totalAreas}</p>
          </div>
          <FontAwesomeIcon icon={faBookOpen} className="w-8 h-8 text-emerald-600 dark:text-emerald-500" />
        </div>
      </div>

      <div className="bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Average Progress</p>
            <p className="text-2xl font-bold text-gray-800 dark:text-white">{avgProgress}%</p>
          </div>
          <FontAwesomeIcon icon={faArrowTrendUp}  className="w-8 h-8 text-blue-600 dark:text-blue-500" />
        </div>
      </div>

      <div className="bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Excellent</p>
            <p className="text-2xl font-bold text-emerald-600">{excellentAreas}</p>
          </div>
          <div className="w-8 h-8 bg-emerald-600 dark:bg-emerald-500 rounded-full flex items-center justify-center">
            <span className="text-white font-bold text-sm">✓</span>
          </div>
        </div>
      </div>

      <div className="bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 dark:text-gray-400">Needs Attention</p>
            <p className="text-2xl font-bold text-red-600 dark:text-red-500">{needsAttentionAreas}</p>
          </div>
          <div className="w-8 h-8 bg-red-600 dark:bg-red-500 rounded-full flex items-center justify-center">
            <span className="text-white font-bold text-sm">!</span>
          </div>
        </div>
      </div>
    </div>
  )
}

const AreaProgressPage = () => {
  // Admin check
  const isAdmin = adminHelper()
  const [areas, setAreas] = useState([])
  const [filteredAreas, setFilteredAreas] = useState([])
  const [programs, setPrograms] = useState([])
  const [searchTerm, setSearchTerm] = useState('')
  const [filters, setFilters] = useState({
    program: '',
    progressLevel: '',
    sortBy: 'name'
  })
  // programChart removed: we'll use filters.program to drive both list and chart

  // Loading and error states
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [showStatusModal, setShowStatusModal] = useState(false)
  const [statusMessage, setStatusMessage] = useState('')
  const [statusType, setStatusType] = useState('success')

  // Modal states
  const [showAreaDetail, setShowAreaDetail] = useState(false)
  const [selectedArea, setSelectedArea] = useState(null)

  const [viewMode, setViewMode] = useState('grid'); // grid or list

  // FETCH PROGRAMS
  useEffect(() => {
    const fetchPrograms = async () => {
      try {
        const res = await apiGet('/api/program', { withCredentials: true })
        if (Array.isArray(res.data.programs)) {
          const programsData = res.data.programs.map(program => ({
            code: program.programCode,
            name: program.programName,
            id: program.programID,
            color: program.programColor
          }))
          setPrograms(programsData)
        } else {
          setPrograms([])
        }
      } catch (err) {
        console.error("Error occurred when fetching programs", err)
        setError("Failed to fetch programs")
        setStatusMessage("Failed to fetch programs")
        setStatusType("error")
        setShowStatusModal(true)
      }
    }
    fetchPrograms()
  }, [])

  // FETCH AREAS WITH PROGRESS
  useEffect(() => {
    const fetchAreas = async () => {
      setLoading(true)
      try {
        const res = await apiGet('/api/area', { withCredentials: true })
        if (Array.isArray(res.data.area)) {
          // Process the area data to match your component structure
          const processedAreas = res.data.area.map(area => ({
            id: area.areaID,               
            areaNum: area.areaNum,                     
            description: area.areaTitle,
            progress: area.progress || 0,
            programCode: area.programCode,
            programName: area.programName,
            programID: area.programID,
            lastUpdated: area.updated_at ? new Date(area.updated_at).toLocaleDateString() : new Date().toLocaleDateString()
          }))

          // Remove duplicates based on areaID
          const uniqueAreas = processedAreas.filter((area, index, self) => 
            index === self.findIndex(a => a.id === area.id)
          )
          setAreas(uniqueAreas)
        } 
        else {
          setAreas([])
        }
      } catch (err) {
        console.error("Error occurred when fetching areas", err)
        setError("Failed to fetch areas")
        setStatusMessage("Failed to fetch area data")
        setStatusType("error")
        setShowStatusModal(true)
      } finally {
        setLoading(false)
      }
    }
    fetchAreas()
  }, [])

  useEffect(() => {
    let filtered = [...areas]

    // Apply search filter
    if (searchTerm) {
      filtered = filtered.filter(area => 
        (area.description && area.description.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (area.areaNum && area.areaNum.toString().toLowerCase().includes(searchTerm.toLowerCase())) ||
        (area.programCode && area.programCode.toLowerCase().includes(searchTerm.toLowerCase()))
      )
    }

    // Apply program filter
    if (filters.program) {
      filtered = filtered.filter(area => area.programCode === filters.program)
    }

    // Apply progress level filter
    if (filters.progressLevel) {
      switch (filters.progressLevel) {
        case 'excellent':
          filtered = filtered.filter(area => area.progress >= 80)
          break
        case 'good':
          filtered = filtered.filter(area => area.progress >= 60 && area.progress < 80)
          break;
        case 'fair':
          filtered = filtered.filter(area => area.progress >= 40 && area.progress < 60)
          break
        case 'needs-attention':
          filtered = filtered.filter(area => area.progress < 40)
          break
      }
    }

    // Apply sorting
    switch (filters.sortBy) {
      case 'progress-high':
        filtered.sort((a, b) => b.progress - a.progress)
        break
      case 'progress-low':
        filtered.sort((a, b) => a.progress - b.progress)
        break
      case 'updated':
        filtered.sort((a, b) => new Date(b.lastUpdated) - new Date(a.lastUpdated))
        break
      case 'name':
        filtered.sort((a, b) => (a.description || '').localeCompare(b.description || ''))
        break
      default:
        filtered.sort((a, b) => (a.areaNum || '').toString().localeCompare((b.areaNum || '').toString()))
        break
    }

    // Add program color in each area
    const updatedFiltered = filtered.map((filteredArea) => {
      const areaProgram = programs.find(program => program.code === filteredArea.programCode)
      console.log('areaProgram: ', areaProgram)
      return ({...filteredArea, areaColor: areaProgram && areaProgram.color})
    })
    setFilteredAreas(updatedFiltered)
  }, [areas, searchTerm, filters, programs])

  const handleFilterChange = (filterType, value) => {
    setFilters(prev => ({ ...prev, [filterType]: value }))
  };

   const handleAreaClick = (area) => {
    console.log('Area clicked:', area)
    setSelectedArea(area)
    setShowAreaDetail(true)
  };

  const handleCloseAreaDetail = () => {
    setSelectedArea(null)
    setShowAreaDetail(false)
  };

  const refreshData = async () => {
    setLoading(true)
    try {
      // Refetch both programs and areas
      const [programRes, areaRes] = await Promise.all([
        apiGet('/api/program', { withCredentials: true }),
        apiGet('/api/area', { withCredentials: true })
      ])

      // Update programs
      if (Array.isArray(programRes.data.programs)) {
        const programsData = programRes.data.programs.map(program => ({
          code: program.programCode,
          name: program.programName,
          id: program.programID
        }))
        setPrograms(programsData)
      }

      // Update areas
      if (Array.isArray(areaRes.data.area)) {
        const processedAreas = areaRes.data.area.map(area => ({
          id: area.areaID,                   
          areaNum: area.areaNum,            
          description: area.areaTitle,
          progress: area.progress || 0,
          programCode: area.programCode,
          programName: area.programName,
          programID: area.programID,
          lastUpdated: area.updated_at ? new Date(area.updated_at).toLocaleDateString() : new Date().toLocaleDateString()
        }))

        const uniqueAreas = processedAreas.filter((area, index, self) => 
          index === self.findIndex(a => a.id === area.id)
        )

        setAreas(uniqueAreas)
      }

      setStatusMessage("Data refreshed successfully")
      setStatusType("success")
      setShowStatusModal(true)
    } catch (err) {
      console.error("Error refreshing data", err)
      setStatusMessage("Failed to refresh data")
      setStatusType("error")
      setShowStatusModal(true)
    } finally {
      setLoading(false)
    }
  }

  if (loading && areas.length === 0) {
    return (
      <div className="w-full p-5 bg-neutral-200 border border-neutral-300 text-neutral-800 rounded-[20px] shadow-inner shadow-gray-400 dark:bg-gray-900 dark:shadow-emerald-900 dark:text-white min-h-screen">
        <div className="flex items-center justify-center h-64">
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-emerald-600 mx-auto mb-4"></div>
            <p className="text-lg text-gray-600 dark:text-gray-400">Loading area progress...</p>
          </div>
        </div>
      </div>
    )
  }

  // Processed data for bar chart
  const displayedAreas = (filters.program === '' || !filters.program) ? areas : areas.filter(area => area.programCode === filters.program)
  const groupedAreas = Object.values(displayedAreas.reduce((acc, curr)=> {
    if(!acc[curr.areaNum]) {
      acc[curr.areaNum] = {areaNum: curr.areaNum, totalProgress: 0, count: 0}
    }
    acc[curr.areaNum].totalProgress += (curr.progress || 0)
    acc[curr.areaNum].count += 1
    return acc
  }, {})).map(group => ({
    areaNum: group.areaNum,
    totalProgress: group.count ? Math.round(group.totalProgress / group.count) : 0
  }))
  console.log('grouped areas: ', groupedAreas)

  return (
    <div className="w-full p-5 bg-neutral-200 border border-neutral-300 text-neutral-800 rounded-[20px] shadow-inner shadow-gray-400 dark:bg-gray-900 dark:shadow-emerald-900 dark:text-white min-h-screen">
      {/* Status Modal */}
      {showStatusModal && (
        <StatusModal 
          message={statusMessage} 
          type={statusType} 
          showModal={showStatusModal} 
          onClick={() => setShowStatusModal(false)} 
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Area Progress Overview</h1>
        <div className="flex items-center gap-4">
          {/* Refresh Button */}
          <button onClick={refreshData} disabled={loading} className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors duration-300" >
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>

          {/* Search */}
          <div className="relative">
            <FontAwesomeIcon icon={faSearch} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
            <input
              type="text"
              placeholder="Search areas..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-gray-200 inset-shadow-sm inset-shadow-gray-400  dark:bg-gray-700 text-gray-700 dark:text-white focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            />
          </div>
        </div>
      </div>

      {/* Statistics Panel */}
      {areas.length > 0 && <StatsPanel areas={areas} />}

      {/* Error State */}
      {error && !loading && (
        <div className="mb-6 p-4 bg-red-100 dark:bg-red-900/20 border border-red-300 dark:border-red-700 rounded-lg">
          <p className="text-red-700 dark:text-red-400">{error}</p>
          <button 
            onClick={refreshData}
            className="mt-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
          >
            Try Again
          </button>
        </div>
      )}

         {/* Filters */}
      <div className="mb-2">
        <div className="flex items-center gap-2 mb-4">
          <FontAwesomeIcon icon={faFilter} className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          <h2 className="text-lg font-semibold">Filters</h2>
        </div>
        <FilterPanel 
          filters={filters} 
          onFilterChange={handleFilterChange}
          programs={programs}
        />
      </div>

      <div className="grid grid-cols-2 place-self-end text-gray-600 border rounded-lg border bg-gray-300 my-2 w-30 border-gray-400 text-gray-600 dark:text-gray-400 shadow-xl">
        <div 
          onClick={() => setViewMode('grid')}
          title="Grid Layout"
          className={`${viewMode === 'grid' ? "bg-zuccini-500 inset-shadow-gray-700 inset-shadow-sm" : ""} px-5 py-3 rounded-tl-lg rounded-bl-lg text-center`}>
          <FontAwesomeIcon icon={faLayerGroup} />
        </div>
        <div 
          onClick={() => setViewMode('list')}
          title="List Layout"
          className={`${viewMode === 'list' ? "bg-zuccini-500 inset-shadow-gray-700 inset-shadow-sm" : ""} px-5 py-3 rounded-tr-lg rounded-br-lg text-center`}>
          <FontAwesomeIcon icon={faRectangleList} />
        </div>
      </div>

      {/* Graphs */}
      <section className={`mb-8 grid ${viewMode === 'grid' ? "grid-cols-1" : "grid-cols-2"} gap-4`}>        
        <div className='flex max-h-[600px] flex-col items-center justify-center p-4 w-full  text-neutral-800 border-1 dark:border-gray-700 border-gray-300 rounded-3xl shadow-xl transition-all duration-500 inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-900 [&_*:focus]:outline-none ' >        
          {groupedAreas.length === 0 ? (           
            <div className='flex h-[300px] flex-col items-center justify-center p-4 w-full'>
              <FontAwesomeIcon icon={faChartPie} className="text-gray-500 text-7xl mb-5" /> 
              <p className='text-gray-500 text-lg' >
                This program have no areas
              </p>            
              <p className="text-sm text-gray-400">Try adjusting your search or filters.</p>
            </div>
          ) : (
            <>
              <div className="flex flex-col h-full items-center justify-center mb-1">                
                  <h2 className="text-2xl font-semibold">Area Progress Distribution</h2>                  
                  <p className="text-md text-gray-600">{filters.program ? programs.find(p => p.code === filters.program)?.name || 'Unknown Program' : 'All Departments'} — {groupedAreas.length} area(s)</p>     
              </div>
              <ResponsiveContainer width="100%" height={450}>
                <BarChart
                  data={groupedAreas}
                  margin={{ top: 30, right: 30, left: 10, bottom: 80 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#ccc" />
                  <XAxis
                    dataKey="areaNum"
                    interval={0}
                    tick={{ fontSize: 11, fill: '#374151' }}
                    angle={-45}
                    textAnchor="end"
                    height={80}
                    label={{ value: 'Area Number', position: 'insideBottom', offset: -10, style: { fontSize: 14, fontWeight: 'bold' } }}
                  />
                  <YAxis 
                    domain={[0, 100]} 
                    tickCount={6} 
                    tick={{ fontSize: 11, fill: '#374151' }}
                    label={{ value: 'Progress (%)', angle: -90, position: 'insideLeft', style: { fontSize: 14, fontWeight: 'bold' } }}
                  />
                  <Tooltip 
                    formatter={(value) => [`${value}%`, 'Progress']}
                    contentStyle={{ backgroundColor: '#fff', border: '1px solid #ccc', borderRadius: '8px' }}
                  />
                  <Legend 
                    wrapperStyle={{ paddingBottom: '20px' }}
                    fontSize={14}
                    textAlign="center"
                    verticalAlign="top"             
                    iconType="square"
                  />
                  <Bar 
                    dataKey="totalProgress" 
                    name="Progress" 
                    fill="#10b981" 
                    radius={[8, 8, 0, 0]}
                    maxBarSize={60}
                  >
                    <LabelList 
                      dataKey="totalProgress" 
                      formatter={(value) => `${value}%`} 
                      position="top"
                      style={{ fontSize: 12, fontWeight: 'bold', fill: '#059669' }}
                    />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </>
          )}
        </div>
        {viewMode === 'list' ? (          
          <div className={`relative p-3 md:p-5 text-neutral-800 border-1 dark:border-gray-700 border-gray-300 rounded-3xl shadow-xl transition-all duration-500 inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-900`}>
					<h2 className="text-xl font-semibold mb-4">
            Areas ({filteredAreas.length} of {areas.length})
          </h2>
          <div className="space-y-3 bg-gray-300 dark:bg-gray-950/50 dark:border-gray-950/50 p-2 border-5 border-gray-300 rounded-lg overflow-y-auto max-h-[500px]">
            {filteredAreas.length > 0 ? filteredAreas.map((area) => (
              <div
                key={area.areaID} 
                onClick={handleAreaClick}
                className="flex items-center animate-appear justify-between p-4 bg-gray-200 dark:bg-gray-900 border border-neutral-300 dark:border-neutral-700 rounded-lg hover:border-zuccini-500 dark:hover:border-zuccini-600 transition-all duration-300 cursor-pointer group"
                >
                {/* Left side - Progress and Area Info */}
                <div className="flex items-center gap-6">
                  <CircularProgressBar 
                  progress={area.progress || 0} 
                  circleWidth="60" 
                  placement="relative"
                  />
                  
                  <div className="flex flex-col">
                  <div className="flex items-center gap-3 mb-1">
                    <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                    {area.areaNum}
                    </h1>
                    <span className="px-3 py-1 text-sm font-light border border-neutral-400 dark:border-neutral-600 bg-neutral-100 dark:bg-gray-800 rounded-full text-gray-700 dark:text-gray-300">
                    {area.programCode}
                    </span>
                  </div>
                  <h2 className="text-base text-gray-600 dark:text-gray-400">
                    {area.description}
                  </h2>
                  </div>
                </div>

                {/* Right side - Arrow indicator */}
                <div className="opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <svg 
                  className="w-6 h-6 text-zuccini-600 dark:text-zuccini-500" 
                  fill="none" 
                  stroke="currentColor" 
                  viewBox="0 0 24 24"
                  >
                  <path 
                    strokeLinecap="round" 
                    strokeLinejoin="round" 
                    strokeWidth={2} 
                    d="M9 5l7 7-7 7" 
                  />
                  </svg>
                </div>
              </div>
            )
          ) : (              
            <div className="flex flex-col items-center justify-center py-16 w-full">
              <FontAwesomeIcon icon={faBookOpen} className="text-7xl text-gray-400 mb-4" />
              <p className="text-lg text-gray-500">No areas found matching your criteria.</p>
              <p className="text-sm text-gray-400">Try adjusting your search or filters.</p>
            </div>
            )}
          </div>
        </div>

        ) : (
          <></>
        )}
        
      </section>

  
      {/* Areas Grid */}
      {viewMode === 'grid' ? (
        <div className="flex flex-wrap gap-4 p-4 bg-gray-200 inset-shadow-sm inset-shadow-gray-400 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        <h2 className="text-xl font-semibold mb-4">
          Areas ({filteredAreas.length} of {areas.length})
        </h2>
        
        {filteredAreas.length > 0 ? (
          <div className="grid grid-cols-1 max-h-[450px] overflow-y-scroll md:grid-cols-2 lg:grid-cols-3 gap-3">
            {filteredAreas.map((area) => (
              <Area
                onClick={handleAreaClick}
                key={area.id}
                areaTitle={area.areaNum}
                desc={area.description}
                program={area.programCode}
                progress={area.progress}
                areaColor={area.areaColor}
              />
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-16 w-full">
            <FontAwesomeIcon icon={faBookOpen} className="text-7xl text-gray-400 mb-4" />
            <p className="text-lg text-gray-500">No areas found matching your criteria.</p>
            <p className="text-sm text-gray-400">Try adjusting your search or filters.</p>
          </div>
        )}
      </div>
      ) : (
        <></>
      )}
      

      {showAreaDetail && selectedArea && (
        <AreaDetailModal
          area={selectedArea}
          showModal={showAreaDetail}
          onClick={handleCloseAreaDetail}
        />
      )}
    </div>
  );
};

export default AreaProgressPage