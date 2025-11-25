import{faCalendarPlus, faAngleRight, faChartArea, faCalendarWeek, faGraduationCap, faBullhorn, faPlus, faGears, faHourglassHalf, faCalendarDays, faTrash} from '@fortawesome/free-solid-svg-icons'
import {Link, Navigate, Route, useNavigate} from 'react-router-dom';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useRef, useEffect, useState } from 'react';
import { apiGet, apiPost, apiDelete, API_URL, apiPostForm } from '../utils/api_utils';
import toast from 'react-hot-toast';
import { Toaster } from 'react-hot-toast';
import { getCurrentUser, adminHelper } from '../utils/auth_utils';
import AnnouncementModal from '../components/modals/AnnouncementModal';
import StatusModal from '../components/modals/StatusModal';
import EventModal from '../components/modals/EventModal';
import DeadlineModal from '../components/modals/DeadlineModal';
import FullCalendar from '@fullcalendar/react';
import dayGridPlugin from '@fullcalendar/daygrid';
import CircularProgressBar from '../components/CircularProgressBar';


const Dashboard = () => {
const [showStatusModal, setShowStatusModal] = useState(false);
const [statusMessage, setStatusMessage] = useState("");
const [statusType, setStatusType] = useState("success");
const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
const [selectedAnnouncement, setSelectedAnnouncement] = useState(null);

const [showCreateDeadline, setShowCreateDeadline] = useState(false);
const [selectedDeadline, setSelectedDeadline] = useState(null);
const [selectedEvent, setSelectedEvent] = useState(null);

const [showAnnounceModal, setShowAnnounceModal] = useState(false);
const [announcements, setAnnouncements] = useState([]);
const [announcementsLoading, setAnnouncementsLoading] = useState(true);
const isAdmin = adminHelper()
const [count, setCount] = useState({
	employees: 0,
	programs: 0,
	institutes: 0,
	deadlines: 0
})
const [countLoading, setCountLoading] = useState(true)
const user = getCurrentUser()
const key = user?.employeeID ? `welcomeShown:${user.employeeID}` : 'WelcomeShown'
// Fetch announcements
const fetchAnnouncements = async () => {
	try {
		setAnnouncementsLoading(true)
		const response = await fetch(`${API_URL}/api/announcements`, {
			method: 'GET',
			credentials: 'include',
			headers: {'Content-Type': 'application/json'}
		})
		const data = await response.json();
		if (data && Array.isArray(data)) {setAnnouncements(data)} 
		else {
			console.log('📢 No announcements or invalid response')
			setAnnouncements([])
		}
	} 
	catch(error) {
		console.error('Error fetching announcements:', error)
		setAnnouncements([])
	} 
	finally {setAnnouncementsLoading(false)}
}

	useEffect(()=> {
		const fetchCounts = async () => {
			try{
				setCountLoading(true)
				const response = await apiGet('/api/count')
				if (response.success) {setCount(response.data)} 
				else {
					console.error("Failed fetching counts", response.error)
					// Keep default values (0) if API fails
				}
			} 
			catch(err){
				console.error("Failed fetching counts", err)
				// Keep default values (0) if API fails
			} 
			finally {setCountLoading(false)}
		}
		fetchCounts()
		fetchAnnouncements()
		// Check if this is a fresh login (not a page refresh or navigation)
		const hasShownWelcome = sessionStorage.getItem(key)
		if (!hasShownWelcome && user?.employeeID) {
			toast.success(`Welcome, ${user.lastName} | ${user.employeeID}!`, { duration: 2000, icon: '🎊' })    
			sessionStorage.setItem(key, 'true')
		}  
	}, [])

	const handleCreateAnnouncement = async (announcement) => {
		console.log("New announcement:", announcement)
		// Here you can push it to state, API call, etc.
		try {
			const response = await apiPost('/api/announcement/post', {
				title: announcement.title, 
				message: announcement.message, 
				duration: announcement.duration,            
			})
			setShowStatusModal(true)
			setStatusMessage(response.data.message)
			setStatusType("success")
			// Refresh announcements after creating new one
			fetchAnnouncements()
		} 
		catch(err){ 
			console.error('Posting announcement to server failed, ', err)
			setShowStatusModal(true)
			setStatusMessage("Failed to post announcement.")
			setStatusType("error")
		}
	}

	// Delete announcement function
	const handleDeleteAnnouncement = async (announcementId) => {
		if (!isAdmin) {
			toast.error('Only admins can delete announcements')
			return
		}        
	
		try {
			const response = await apiDelete(`/api/announcement/delete/${announcementId}`)
			console.log('🗑️ Delete response:', response)
			if (response.success) {
					toast.success('Announcement deleted successfully')
					setShowDeleteConfirm(false)
					fetchAnnouncements() // Refresh the list
			} 
			else {toast.error(response.error || 'Failed to delete announcement')}
		} 
		catch(error) {
			console.error('Error deleting announcement:', error)
			toast.error('Failed to delete announcement')
		}
	}

	// Fetch logs
	const [logs, setLogs] = useState([])
	useEffect(()=> {
		const fetchLogs = async ()=> {
			try {
				const response = await apiGet('/api/auditLogs')
				const logsData = response?.data?.logs || response?.data?.data?.logs || []
				setLogs(Array.isArray(logsData) ? logsData : [])
			} 
			catch(err) {
				console.error('Error getting logs ', err)
				setLogs([])
			}
		} 
		fetchLogs()
	}, [])

	// Fetch pending documents
	const [pendingDocs, setPendingDocs] = useState([])
	useEffect(()=> {
		const fetchPendingDocs = async ()=> {
			try {
				const response = await apiGet('/api/pendingDocs')
				const pd = response?.data?.pendingDocs || response?.data?.data?.pendingDocs || []
				setPendingDocs(Array.isArray(pd) ? pd : [])
			} 
			catch(err) {
				console.error('Error getting pending documents ', err)
				setPendingDocs([])
			}
		} 
		fetchPendingDocs()
		console.log('Pending docs: ', pendingDocs)
	}, [])

	// Function to get the location of pending doc from its filePath
	function parseDocumentPath(pendingDoc) {
		if (!pendingDoc?.pendingDocPath || typeof pendingDoc.pendingDocPath !== 'string') {
			console.warn('⚠️ Invalid pendingDocPath:', pendingDoc)
			return {
			programCode: '',
			areaName: '',
			subareaName: '',
			criteria: '',
			criteriaNum: '',
			documentName: ''
			}
		}
		const pathParts = pendingDoc.pendingDocPath.split('/')
		const programIndex = pathParts.findIndex(part => part === 'Programs')
		return {
			programCode: pathParts[programIndex + 1] || '',
			areaName: pathParts[programIndex + 2] || '',
			subareaName: pathParts[programIndex + 3] || '',
			criteria: pathParts[programIndex + 4] || '',
			criteriaNum: pathParts[programIndex + 5] || '',
			documentName: pathParts[programIndex + 6] || ''
		}
	}

// Navigate to accreditation with parsed path information
const navigate = useNavigate()
function handlePendingDocClick(pathInfo) {
	navigate('/Accreditation', {
		state: {
			programCode: pathInfo.programCode,
			areaName: pathInfo.areaName,
			subareaName: pathInfo.subareaName,
			criteria: pathInfo.criteria,
			criteriaNum: pathInfo.criteriaNum,
			documentName: pathInfo.documentName
		}
	})
}

// Fetch all areas
const [allAreas, setAllAreas]= useState([])
useEffect(() => {
	const fetchArea = async () => {
		try{
			const res = await apiGet('/api/area', {withCredentials: true})
			Array.isArray(res.data.area) ? setAllAreas(res.data.area) : setAllAreas([]);
			Array.isArray(res.data.area) ? setAreaProgressList(res.data.area) : setAreaProgressList([]);
		} catch(err) {console.error("Failed to fetch area", err)}
	}
	fetchArea()
	}, [])

// Filter areas for form options
const [filteredAreaOptions, setFilteredAreaOptions] = useState([])
const [program, setProgram] = useState("")
useEffect(()=> {
	if(program){
		const filteredAreas = allAreas.filter((area) => String(area.programID) === String(program))
		setFilteredAreaOptions(filteredAreas)
		setSelectedAreaOption("")
	} 
	else {setFilteredAreaOptions([])}
}, [program, allAreas])

// Fetch programs for form option
const [programOption, setProgramOption] = useState([])
useEffect(() => {
	const fetchProgram = async () => {
		try{
			const res = await apiGet('/api/program', {withCredentials: true})
			Array.isArray(res.data.programs) ? setProgramOption(res.data.programs) : setProgramOption([]);
		} catch(err) {console.error("Error occurred when fetching program", err)}
	}
	fetchProgram();
}, [])

const [dueDate, setDueDate] = useState("")
const [content, setContent] = useState("")
const [selectedAreaOption, setSelectedAreaOption] = useState("")


// Creation of deadline
const handleCreateDeadline = async (e) => {
    e.preventDefault()
    if (!isAdmin && !user.isCoAdmin) return 
    const formData = new FormData()
    formData.append("program", program)
    formData.append("area", selectedAreaOption)  // ✅ Changed from selectedArea    
    formData.append("due_date", dueDate)
    formData.append("content", content)
    try{
        //create deadline api
        const res = await apiPostForm('/api/deadline', formData, {withCredentials: true}) 
        setStatusMessage(res.data.message)
        setShowStatusModal(true)
        setStatusType("success")
        setSelectedAreaOption("")
        setProgram("")
        setContent("")        
        setDueDate("")

		setShowCreateDeadline(false)
        // refetch deadline data
        const deadlineRes = await apiGet("api/deadlines", {withCredentials: true})
        Array.isArray(deadlineRes.deadline) ? setDeadLines(deadlineRes.deadline) : setDeadLines([])  
        // refetch event data
        const eventRes = await apiGet("/api/events", {withCredentials: true})
        Array.isArray(eventRes.data) ? setEvent(eventRes.data) : setEvent([])
    }
    catch(err) {
        setStatusMessage("Server error. Please try again");
        setShowStatusModal(true);
        setStatusType("error");
        console.error(err.res?.data || err.message);
    }
}

// Fetch deadlines
const [deadLines, setDeadLines] = useState([])
useEffect(() => {
	const fetchDeadline = async () => {
		try{
			const res = await apiGet("/api/deadlines", {withCredentials: true})
			Array.isArray(res.data.deadline) ? setDeadLines(res.data.deadline) : setDeadLines([])
		} catch (err){console.error("Error occurred when fetching deadlines! ", err)}
	}
	fetchDeadline()
}, [])

// FETCH EVENTS (FOR CALENDAR)
const [event, setEvent] = useState([])
useEffect(() => {
	const fetchEvents = async () => {
		try{
			const res = await apiGet("/api/events", {withCredentials: true})
			Array.isArray(res.data) ? setEvent(res.data) : setEvent([]) 
		} catch (err){console.error("Error occurred when fetching events! ", err)}
	}
	fetchEvents()
}, [])

// Event modal
const [showEventModal, setShowEventModal] = useState(false)
const handleEventClick = (clickInfo) => {
	setSelectedEvent({
		title: clickInfo.event.title,
		date: clickInfo.event.startStr,
		color: clickInfo.event.extendedProps.color,
		content: clickInfo.event.extendedProps.content,
	})
	setShowEventModal(true)
}
const handleCloseModal = () =>{setSelectedEvent(null); setShowEventModal(false)}

// View deadline
const [showDeadline, setShowDeadline] = useState(false)
const handleViewDeadline = (selectedDeadline) => {
    setSelectedDeadline({
        id: selectedDeadline.deadlineID,
        programName: selectedDeadline.programName,
        programCode: selectedDeadline.programCode,
        color: selectedDeadline.programColor,
        criteria: selectedDeadline.criteria || [],
        areaName: selectedDeadline.areaName,
        date: selectedDeadline.due_date,
        content: selectedDeadline.content
    });
    setShowDeadline(true);
}

const handleCloseDeadline = () =>{setSelectedDeadline(null); setShowDeadline(false)}

const [areaProgressList, setAreaProgressList] = useState([]) // displays the area in tasks
const uniqueAreas = areaProgressList.filter((area, index, self) => index === self.findIndex(a => a.areaID === area.areaID))

const deadLineRef = useRef(null);
const ScrollToDeadlines = () => {
	if (deadLineRef.current) {
		deadLineRef.current.scrollIntoView({behavior: 'smooth'})
	}
}



return (
	<>	
	{/* Dashboard links */}	
	<section className='grid grid-rows-[auto_1fr] gap-1 mt-20 lg:mt-8 lg:grid-cols-2 lg:grid-rows-1'>   
		<DashboardLinks icon={faGraduationCap} text="Programs" onClick={() => navigate(`/Programs`)} count={count?.programs || 0} loading={countLoading}/>            
		<DashboardLinks icon={faCalendarDays} text="Deadlines" onClick={ScrollToDeadlines} count={count?.deadlines || 0} loading={countLoading}/>            
	</section>
			

	{/* Announcements */}
	<section className={`relative mt-4 mb-8 p-3 md:p-5 text-neutral-800 border-1 dark:border-gray-700 border-gray-300 rounded-3xl shadow-xl transition-all duration-500 inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-900`}>
		<div className='flex flex-row items-center'>
			<FontAwesomeIcon icon={faBullhorn} className="p-2 dark:text-white" />
			<h2 className="mb-1 font-semibold lg:mb-4 text-md lg:text-xl text-neutral-800 dark:text-white">Announcements</h2>
		</div>

		{isAdmin && (
			<div onClick={() => {if (!isAdmin){toast.error('Admins only'); return} setShowAnnounceModal(true)}} className="absolute flex flex-row items-center justify-around px-2 py-0 transition-all duration-500 cursor-pointer md:px-5 md:py-1 top-4 md:top-5 right-5 rounded-3xl hover:bg-zuccini-600 active:bg-zuccini-500" >
				<FontAwesomeIcon icon={faPlus} className="mr-2 dark:text-white" />
				<h1 className="text-lg dark:text-white" >New</h1>
			</div>
		)}
				
		<div className="p-4 transition-all duration-500 rounded-lg bg-neutral-300 dark:bg-gray-950/50">
			{announcementsLoading ? (<p className="p-5 font-light text-center text-gray-700 transition-all duration-500 dark:text-white">Loading announcements...</p>) : announcements && announcements.length > 0 ? (
				<div className="space-y-3 max-h-[400px] overflow-y-auto" >
					{announcements.map((announcement, index) => (
						<div key={index} className="p-2 bg-gray-100 border border-gray-300 rounded-lg shadow-sm md:p-4 dark:bg-gray-800 dark:border-gray-700">
							<div className="flex flex-col items-start justify-between mb-2 md:flex-row">
								<h3 className="font-semibold text-gray-800 dark:text-white">{announcement.announceTitle}</h3>
								<div className="flex items-center gap-2">
									<span className="text-sm text-gray-500 dark:text-gray-400">
										{announcement.duration ? new Date(announcement.duration).toLocaleDateString() : 'No date'}
									</span>
									<button onClick={() => {setShowDeleteConfirm(true); setSelectedAnnouncement(announcement)}}	className="px-2 py-1 text-xs text-red-600 transition-colors rounded hover:bg-red-100 dark:hover:bg-red-900" >Delete</button>
								</div>
							</div>

							<p className="mb-2 text-sm text-gray-600 dark:text-gray-300">{announcement.announceText}</p>
							<p className="text-xs text-gray-500 dark:text-gray-400">By: {announcement.author}</p>
						</div>
					))}
				</div>
			) : (<p className="p-5 font-light text-center text-gray-700 transition-all duration-500 dark:text-white">No new announcements</p>)}
		</div>
	</section>

	{showDeleteConfirm && (
		<div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"> 
			<div className='absolute flex flex-col items-center justify-center p-4 border border-gray-200 shadow-lg bg-red-50 w-100 rounded-xl dark:bg-gray-700 dark:border-gray-600 fade-in'>
				<div className='flex items-center justify-center mb-4 bg-red-200 rounded-full inset-shadow-sm w-18 h-18 inset-shadow-red-300'><FontAwesomeIcon icon={faTrash} className="m-auto text-4xl text-red-500"/></div>
				<h3 className='mb-2 text-xl font-bold text-gray-900 dark:text-white'>Delete Announcement</h3>
				<span className='mb-6 text-center text-gray-600 break-words dark:text-gray-300'>Are you sure you want to delete "<strong>{selectedAnnouncement.announceTitle}</strong>"?</span>
				<div className='flex gap-4'>
					<button onClick={() => handleDeleteAnnouncement(selectedAnnouncement.announceID)} className='px-4 py-2 text-white bg-red-500 rounded-lg hover:bg-red-600 dark:bg-red-600 dark:hover:bg-red-700' >Yes</button>
					<button onClick={(e) => {e.stopPropagation();setShowDeleteConfirm(false)}} className='px-4 py-2 text-gray-800 bg-gray-200 rounded-lg hover:bg-gray-300 dark:text-white dark:bg-gray-600 dark:hover:bg-gray-700' >No</button>
				</div>                                    
			</div>
		</div>
	)}

	{showAnnounceModal && (<AnnouncementModal setShowModal={setShowAnnounceModal} onCreate={handleCreateAnnouncement}/>)}

	{/* Area Progress */}
		<section className="relative grid grid-cols-2 gap-3 p-1 min-h-[220px]">
			<div className={`relative p-3 md:p-5 text-neutral-800 border-1 dark:border-gray-700 border-gray-300 rounded-3xl shadow-xl transition-all duration-500 inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-900`}>
				<div className="mb-4">
					<h1 className="text-2xl font-semibold text-zuccini-700/80">
						<FontAwesomeIcon icon={faChartArea} className="mr-2"/>
						Area Progress
					</h1>
					<p className="text-sm text-gray-500 dark:text-gray-400">Overview of all area progress</p>
				</div>
				{/* Areas */}
				{areaProgressList && areaProgressList.length > 0 ? (
				<>
					<div className="space-y-3 bg-gray-300 dark:bg-gray-950/50 dark:border-gray-950/50 p-2 border-5 border-gray-300 rounded-lg overflow-y-scroll max-h-[500px]">
					{uniqueAreas.slice(0, 10).map((area) => (
						<div
						key={area.areaID} 
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
								{area.areaTitle}
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
					))}
					</div>

					{/* View All Button */}
					<div 
					onClick={() => navigate('/Progress')} 
					className="mt-4 flex items-center justify-center p-4 bg-gradient-to-r from-zuccini-600 to-zuccini-700 dark:from-zuccini-700 dark:to-zuccini-800 rounded-lg hover:from-zuccini-700 hover:to-zuccini-800 dark:hover:from-zuccini-600 dark:hover:to-zuccini-700 transition-all duration-300 cursor-pointer group"
					>
					<h1 className="text-lg font-semibold text-white group-hover:tracking-wide transition-all duration-300">
						View All Areas
					</h1>
					<svg 
						className="w-5 h-5 ml-2 text-white transform group-hover:translate-x-1 transition-transform duration-300" 
						fill="none" 
						stroke="currentColor" 
						viewBox="0 0 24 24"
					>
						<path 
						strokeLinecap="round" 
						strokeLinejoin="round" 
						strokeWidth={2} 
						d="M13 7l5 5m0 0l-5 5m5-5H6" 
						/>
					</svg>
					</div>
				</>			
				) : (
				<p className="text-lg text-center text-gray-500 font-extralight">
					No areas found.
				</p>
				)}
			</div>

			{/* Deadlines */}
			<div ref={deadLineRef} className={`relative p-3 md:p-5 text-neutral-800 border dark:border-gray-700 border-gray-300 rounded-3xl shadow-xl transition-all duration-500 inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-900`}>     
			{/* Header */}
			<div className="mb-4">
				<h1 className="text-2xl font-semibold text-zuccini-700/80">
					<FontAwesomeIcon icon={faCalendarWeek} className="mr-2"/>
					Deadlines
				</h1>
				<p className="text-sm text-gray-500 dark:text-gray-400">Upcoming tasks and due dates</p>
			</div>

			{/* Create Deadline Btn*/}
			{(isAdmin || user.isCoAdmin) && (					
			<button 
				onClick={setShowCreateDeadline}
				className='absolute top-5 right-5 flex items-center gap-2 px-5 py-2.5 font-semibold text-white bg-gradient-to-r from-zuccini-600 to-zuccini-700 dark:from-zuccini-700 dark:to-zuccini-800 hover:from-zuccini-700 hover:to-zuccini-800 dark:hover:from-zuccini-600 dark:hover:to-zuccini-700 rounded-lg shadow-lg hover:shadow-xl transition-all duration-300 cursor-pointer group'>
				<svg 
					className="w-5 h-5 transition-transform duration-300 group-hover:rotate-90" 
					fill="none" 
					stroke="currentColor" 
					viewBox="0 0 24 24"
				>
					<path 
						strokeLinecap="round" 
						strokeLinejoin="round" 
						strokeWidth={2} 
						d="M12 4v16m8-8H4" 
					/>
				</svg>
				<span className="group-hover:tracking-wide transition-all duration-300">
					Create Deadline
				</span>
			</button>
			)}

			{/* Table Header */}
			<div className='grid grid-cols-[2fr_3fr_1.5fr] gap-4 px-4 py-3 mb-2 text-sm font-semibold text-gray-600 dark:text-gray-400 border-b border-neutral-300 dark:border-gray-700'>
				<h2>Program</h2>
				<h2>Task</h2>
				<h2 className="text-right">Due Date</h2>
			</div>

			{/* Deadline Container */}
			<div className='flex flex-col min-h-[500px] overflow-y-auto bg-gray-300 dark:bg-gray-950/50 dark:border-gray-950/50 p-2 rounded-lg' >
				{deadLines && deadLines.length > 0 ? (
					<div className="space-y-2">
						{deadLines.map((deadline) => (
							<div 
								key={deadline.deadlineID} 
								onClick={() => handleViewDeadline(deadline)}  
								className='grid grid-cols-[2fr_3fr_1.5fr] gap-4 items-center px-4 py-3 rounded-lg bg-gray-200 dark:bg-gray-800 border border-neutral-200 dark:border-gray-700 hover:border-zuccini-500 dark:hover:border-zuccini-600 hover:shadow-md transition-all duration-300 cursor-pointer group'
							>
								{/* Program Code */}
								<div className='flex items-center gap-3'>
									<div className="flex items-center justify-center w-8 h-8 rounded-lg bg-zuccini-100 dark:bg-zuccini-900/30 group-hover:bg-zuccini-200 dark:group-hover:bg-zuccini-900/50 transition-colors">
										<FontAwesomeIcon 
											icon={faAngleRight} 
											className="text-zuccini-600 dark:text-zuccini-500" 
										/>
									</div>
									<h2 className='text-lg font-semibold text-gray-800 dark:text-white'>
										{deadline.programCode}
									</h2>
								</div>

								{/* Task/Area Name */}
								<h2 className='text-sm text-gray-600 dark:text-gray-300 line-clamp-2'>
									{deadline.areaName}
								</h2>

								{/* Due Date */}
								<div className="flex items-center justify-end gap-2">
									<div className="p-2 text-sm font-medium rounded-full bg-neutral-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
										{deadline.due_date}
									</div>
								</div>
							</div>
						))}
					</div>
				) : (
					<div className="flex items-center justify-center h-full">
						<div className="text-center">
							<svg 
								className="w-16 h-16 mx-auto mb-4 text-gray-300 dark:text-gray-600" 
								fill="none" 
								stroke="currentColor" 
								viewBox="0 0 24 24"
							>
								<path 
									strokeLinecap="round" 
									strokeLinejoin="round" 
									strokeWidth={1.5} 
									d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" 
								/>
							</svg>
							<p className="text-lg font-medium text-gray-500 dark:text-gray-400">No deadlines ahead</p>
							<p className="text-sm text-gray-400 dark:text-gray-500">You're all caught up!</p>
						</div>
					</div>
				)}            
			</div>

			{/* Display deadlines modal */}
			{showDeadline && selectedDeadline && (
				<DeadlineModal 
					programName={selectedDeadline.programName} 
					programCode={selectedDeadline.programCode} 
					area={selectedDeadline.areaName} 
					criteria={selectedDeadline.criteria || 'No Criteria'}
					date={selectedDeadline.date} 
					color={selectedDeadline.color} 
					content={selectedDeadline.content || 'No description'} 
					id={selectedDeadline.id}
					onClick={handleCloseDeadline}
					showModal={showDeadline}
				/>
			)}
		</div>
		</section>
	
	

	{/* shows status when creating deadline */}	
	<Toaster />
	{showStatusModal && (<StatusModal message={statusMessage} type={statusType} showModal={showStatusModal} onClick={()=>setShowStatusModal(false)} />)} 


	{/* Calendar */}
		<div className="relative row-start-3 p-3 transition-all text-gray-800 duration-500 bg-transparent border shadow-xl md:row-start-2 rounded-2xl border-neutral-300 inset-shadow-sm inset-shadow-gray-400 dark:shadow-sm dark:shadow-zuccini-900 dark:text-white dark:bg-gray-900 ">
			<FullCalendar 
				plugins={[dayGridPlugin]}
				initialView='dayGridMonth'
				headerToolbar={{start: 'title', center: '', end: 'today prev next'}}
				events={event}        
				eventClick={handleEventClick}
				height={'550px'}                    
				expandRows={true}
			/>

			{/* EventModal */}
			{showEventModal && selectedEvent && (
				<EventModal title={selectedEvent.title} showModal={showEventModal} date={selectedEvent.date} content={selectedEvent.content || 'N/A'} onClick={handleCloseModal} />
			)}
		</div>


	{ isAdmin && (
		<section  className='grid grid-cols-2 grid-rows-2 gap-4 mt-4 md:grid-cols-2 lg:grid-rows-1' >

			{/* Pending Documents
			<div className="p-3 mb-5 transition-all duration-500 shadow-xl md:p-5 text-neutral-800 border-1 border-neutral-300 rounded-3xl inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:border-gray-900 dark:bg-gray-900" >
				<div className='flex flex-row'>
					<FontAwesomeIcon icon={faHourglassHalf}  className="p-2 transition-all duration-500 dark:text-white" />
					<h2 className="mb-4 text-xl font-semibold transition-all duration-500 text-neutral-800 dark:text-white">Pending Documents</h2>
				</div>
				<div className="relative flex flex-col gap-1 p-2 overflow-auto rounded-lg whitespace-nowrap h-60 bg-neutral-300 dark:border-gray-900 dark:bg-gray-950/50" >
					{pendingDocs.filter(doc => doc.pendingDocPath && typeof doc.pendingDocPath === 'string').map((pendingDoc)=> {
						const pathInfo = parseDocumentPath(pendingDoc)
						return (
							<p onClick={()=> handlePendingDocClick(pathInfo)} key={pendingDoc.pendingDocID} className="text-gray-800 border-b border-gray-400 cursor-pointer  w-fit hover:bg-gray-400 dark:text-white">
								<span className='font-semibold'>{pendingDoc.pendingDocName}</span><br/>
								{pathInfo.programCode}/{pathInfo.areaName}/{pathInfo.subareaName}/{pathInfo.criteria}/{pathInfo.criteriaNum}
							</p>
						)
					})}
				</div>
			</div> */}

			{/* Audit Logs */}                
			<div className="col-span-2 p-3 mb-5 transition-all duration-500 shadow-xl md:p-5 text-neutral-800 border-1 dark:border-gray-900 border-neutral-300 rounded-3xl inset-shadow-sm inset-shadow-gray-400 dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-900">
				<div className='flex flex-row'>
					<FontAwesomeIcon icon={faGears} className="p-2 transition-all duration-500 dark:text-white" />
					<h2 className="mb-4 text-xl font-semibold transition-all duration-500 text-neutral-800 dark:text-white">Audit Logs</h2>
				</div>

                    {/* Display logs */}                    
                        <div className="overflow-auto rounded-lg h-60 bg-neutral-300 dark:bg-gray-950/50">
                            <table className="w-full">
                                <thead className="sticky top-0 border-b border-gray-400 bg-neutral-400 dark:bg-gray-900 dark:border-gray-800">
                                    <tr>
                                        <th className="px-4 py-2 text-xs font-semibold tracking-wider text-left text-gray-700 uppercase dark:text-gray-300">
                                            Action
                                        </th>
                                        <th className="px-4 py-2 text-xs font-semibold tracking-wider text-right text-gray-700 uppercase dark:text-gray-300">
                                            Date & Time
                                        </th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-400 dark:divide-gray-800">
                                    {logs.map((log) => {
                                        const isLogin = log.action.includes('LOGGED IN') || log.action.includes('Logged in');
                                        const isDelete = log.action.includes('DELETED') || log.action.includes('Deleted') || log.action.includes('deleted');
                                        const isRate = log.action.includes('RATED') || log.action.includes('Rated') || log.action.includes('rated');
                                        const isCreate = log.action.includes('CREATED') || log.action.includes('Created') || log.action.includes('created');
                                        const isUpload = log.action.includes('UPLOADED') || log.action.includes('Uploaded') || log.action.includes('uploaded');
                                        const isLoggedOut = log.action.includes('LOGGED OUT');
                                        const isEdit = log.action.includes('EDITED') || log.action.includes('Edited') || log.action.includes('edited');
                                        const isDownload = log.action.includes('DOWNLOADED') || log.action.includes('Downloaded') ||  log.action.includes('downloaded');
                                        const isUpdate = log.action.includes( 'UPDATED') || log.action.includes('Updated') || log.action.includes('updated');
                                        const isApply = log.action.includes('APPLIED') || log.action.includes('Applied') || log.action.includes('applied');

                                        return (
                                            <tr 
                                                key={log.logID} 
                                                className="transition-colors animation-appear duration-150 hover:bg-gray-400 dark:hover:bg-gray-800/70"
                                            >
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center gap-2">
                                                        {isLogin && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-blue-200 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                                                                Login
                                                            </span>
                                                        )}
                                                        {isDelete && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-red-200 text-red-800 dark:bg-red-900/40 dark:text-red-300">
                                                                Delete
                                                            </span>
                                                        )}
                                                        {isRate && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-orange-200 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300">
                                                                Rate
                                                            </span>
                                                        )}
                                                        {isCreate && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-200 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                                                                Create
                                                            </span>
                                                        )}
                                                        {isUpload && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-purple-200 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
                                                                Upload
                                                            </span>
                                                        )}
                                                        {isLoggedOut && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-amber-200 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
                                                                Logout
                                                            </span>
                                                        )}
                                                        {isEdit && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-teal-200 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300">
                                                                Edit
                                                            </span>
                                                        )}
                                                        {isUpdate && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-teal-200 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300">
                                                                Update
                                                            </span>
                                                        )}
                                                        {isApply && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-purple-200 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
                                                                Apply
                                                            </span>
                                                        )}
                                                        {isDownload && (
                                                            <span className="px-2 py-0.5 rounded-md text-xs font-medium bg-emerald-200 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                                                                Download
                                                            </span>
                                                        )}
                                                        <span className="text-sm text-gray-700 transition-all duration-500 dark:text-white">
                                                            {log.action}
                                                        </span>
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-sm text-right text-gray-700 transition-all duration-500 dark:text-white">
                                                    {new Date(log.createdAt).toLocaleString()}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </section>
            )}

		{/* Display Create deadline modal */}
		{showCreateDeadline && (		
			<div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">			
				<div className="relative w-full max-w-3xl bg-gray-200 dark:bg-gray-900 rounded-2xl shadow-2xl border border-neutral-200 dark:border-gray-700 max-h-[90vh] overflow-y-auto">
					{/* Header */}
					<div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b bg-gradient-to-br from-zuccini-400 to-zuccini-700 dark:bg-gray-900 border-neutral-200 dark:border-gray-700 rounded-t-2xl">
						<div className="flex items-center gap-3">
							<div className="flex items-center justify-center w-10 h-10 rounded-lg bg-zuccini-100 dark:bg-zuccini-900/30">
								<FontAwesomeIcon icon={faCalendarPlus} className="text-zuccini-600 dark:text-zuccini-500" />
							</div>
							<h1 className="text-xl font-semibold text-gray-900 dark:text-white">
								Create Submission Deadline
							</h1>
						</div>
						<button
							onClick={() => setShowCreateDeadline(false)}
							className="flex items-center justify-center w-8 h-8 text-gray-500 transition-colors rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 dark:text-gray-400"
						>
							<svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
								<path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
							</svg>
						</button>
					</div>

					{/* Form */}
					<form onSubmit={handleCreateDeadline} className="p-6">
						{/* Form Fields Grid */}
						<div className="grid grid-cols-1 gap-5 mb-5 md:grid-cols-3">
							{/* Select Program */}
							<div className="flex flex-col">
								<label htmlFor="program" className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
									Program <span className="text-red-500">*</span>
								</label>
								<select 
									name="program" 
									id="program" 
									value={program} 
									onChange={(e) => setProgram(e.target.value)} 
									required  
									className="px-4 py-2.5 text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-zuccini-500 focus:border-zuccini-500 dark:focus:ring-zuccini-600 transition-all outline-none"
								>
									<option value="">Select a Program</option>
									{programOption.map((program) => (
										<option key={program.programID} value={program.programID}>
											{program.programName}
										</option>
									))}
								</select>
							</div>
							
							{/* Select Area */}
							<div className="flex flex-col">
								<label htmlFor="area" className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
									Area <span className="text-red-500">*</span>
								</label>
								<select 
									name="area" 
									id="area" 
									value={selectedAreaOption} 
									onChange={(e) => setSelectedAreaOption(e.target.value)} 
									required  
									className="px-4 py-2.5 text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-zuccini-500 focus:border-zuccini-500 dark:focus:ring-zuccini-600 transition-all outline-none"
								>
									<option value="">Select an Area</option>
									{filteredAreaOptions
										.filter((area, index, self) => index === self.findIndex(a => a.areaID === area.areaID))
										.map((area) => (
											<option key={area.areaID} value={area.areaID}>
												{area.areaName}
											</option>
										))
									}
								</select>
							</div>

							{/* Select Deadline Date */}
							<div className="flex flex-col">
								<label htmlFor="due_date" className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
									Due Date <span className="text-red-500">*</span>
								</label>
								<input 
									type="date" 
									name="due_date" 
									id="due_date" 
									value={dueDate} 
									onChange={(e) => setDueDate(e.target.value)} 
									required  
									className="px-4 py-2.5 text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-zuccini-500 focus:border-zuccini-500 dark:focus:ring-zuccini-600 transition-all outline-none"
								/>  
							</div>
						</div>

						{/* Deadline Description */}
						<div className="flex flex-col mb-6">
							<label htmlFor="content" className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
								Description <span className="text-red-500">*</span>
							</label>
							<textarea 
								name="content" 
								value={content} 
								id="content" 
								placeholder="Enter a detailed description of the deadline..." 
								onChange={(e) => setContent(e.target.value)} 
								required  
								rows={6}
								className="px-4 py-3 text-gray-900 dark:text-white placeholder-gray-400 bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-zuccini-500 focus:border-zuccini-500 dark:focus:ring-zuccini-600 transition-all outline-none resize-y"
							/>
							<p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
								Provide context and any important details about this deadline.
							</p>
						</div>

						{/* Action Buttons */}
						<div className="flex items-center justify-end gap-3 pt-4 border-t border-neutral-200 dark:border-gray-700">
							<button
								type="button"
								onClick={() => setShowCreateDeadline(false)}
								className="px-5 py-2.5 font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
							>
								Cancel
							</button>
							<button
								type="submit"
								className="px-6 py-2.5 font-medium text-white bg-gradient-to-r from-zuccini-600 to-zuccini-700 dark:from-zuccini-700 dark:to-zuccini-800 hover:from-zuccini-700 hover:to-zuccini-800 dark:hover:from-zuccini-600 dark:hover:to-zuccini-700 rounded-lg shadow-md hover:shadow-lg transition-all"
							>
								Create Deadline
							</button>
						</div>
					</form>
				</div>
			</div>
		)}	

			
	</>
)}

export const DashboardLinks = ({icon, text, onClick, count, loading = false}) =>{
	const navigate = useNavigate()
	return (
		<div onClick={onClick} className='relative flex flex-row items-center h-[100px] p-4 m-1 bg-gradient-to-r from-green-400/90 to-teal-600/90 dark:from-green-600/80 dark:to-teal-800/80 transition-all duration-500 shadow-xl cursor-pointer text-neutral-800 border-1 border-neutral-300 inset-shadow-sm inset-shadow-gray-400 dark:border-gray-800 rounded-3xl dark:shadow-md dark:shadow-zuccini-900 dark:bg-gray-900'>
			<div className='flex items-center justify-center p-2 w-12 h-12 bg-gray-200 rounded-full mr-3'><FontAwesomeIcon icon={icon} className="text-2xl text-center text-zuccini-700" /></div>
			<h1 className="text-xl font-semibold transition-all duration-500 text-shadow-sm text-white">{text}</h1>
			<span className="absolute text-lg transition-all duration-500 right-6 text-white">{loading ? '...' : count}</span>
		</div>
	)
}

export const Area = ({onClick, program, areaTitle, desc, progress, areaColor}) =>{
	return(
		<div onClick={onClick} className="relative animate-appear mr-4 min-w-[300px] h-[210px] border-gray-400 dark:border-gray-800 border rounded-lg shadow-xl dark:shadow-sm dark:shadow-zuccini-700 overflow-hidden transition-all duration-500 hover:scale-105 cursor-pointer">
			<div style={{background: areaColor}}  className='h-[50%]'> 
				<div className='absolute px-5 font-light border border-gray-400 top-2 right-2 bg-neutral-200 rounded-xl dark:bg-gray-900 dark:text-white'>{program}</div>
				<CircularProgressBar progress={progress} circleWidth="75" positionX={"left-3"} positionY={"top-17"} placement={`absolute top-17 left-3`}/>           
			</div>      
			<div className='text-right h-[50%] p-3 bg-neutral-200 border-t-1 transition-all duration-500  dark:bg-gray-900 dark:text-white dark:border-t-neutral-600'>
				<h1 className='mb-4 text-2xl font-semibold text-wrap'>{areaTitle}</h1>
				<h2 className='text-lg truncate'>{desc}</h2>
			</div>
		</div> 
	)
}

export default Dashboard;