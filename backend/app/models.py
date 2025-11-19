from app import db
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import TSVECTOR, ARRAY
from sqlalchemy.types import UserDefinedType
class Vector(UserDefinedType):
    def __init__(self, dimensions):
        self.dimensions = dimensions

    def get_col_spec(self, **kw):
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect):
        def process(value):
            return value
        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            return value
        return process


class Employee(db.Model):
    __tablename__ = 'employee'

    employeeID = db.Column(db.String(10), primary_key=True, nullable=False)
    fName = db.Column(db.String(50), nullable=False)
    lName = db.Column(db.String(50))
    suffix = db.Column(db.String(10))
    email = db.Column(db.String(120), nullable=False)
    contactNum = db.Column(db.String(20))
    password = db.Column(db.String(128), nullable=False)
    profilePic = db.Column(db.Text)
    isAdmin = db.Column(db.Boolean, default=False)
    isRating = db.Column(db.Boolean, default=False)
    isEdit = db.Column(db.Boolean, default=False)
    crudFormsEnable = db.Column(db.Boolean, default=False)
    crudProgramEnable = db.Column(db.Boolean, default=False)
    crudInstituteEnable = db.Column(db.Boolean, default=False)
    # isRating = db.Column(db.Boolean, default=False)
    # isEdit = db.Column(db.Boolean, default=False)
    # crudFormsEnable = db.Column(db.Boolean, default=False)
    # crudProgramEnable = db.Column(db.Boolean, default=False)
    # crudInstituteEnable = db.Column(db.Boolean, default=False)
    # isOnline = db.Column(db.Boolean, default=False)
    # experiences = db.Column(db.Text)
    isCoAdmin = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # MFA/OTP fields
    otpcode = db.Column(db.String(6))
    otpexpiry = db.Column(db.DateTime(timezone=True))
    otpverified = db.Column(db.Boolean, default=False)
    
    # Relationships to junction tables
    employee_programs = db.relationship("EmployeeProgram", backref="employee")
    employee_areas = db.relationship("EmployeeArea", backref="employee")
    employee_folders = db.relationship("EmployeeFolder", backref="employee")

class EmployeeProgram(db.Model):
    __tablename__ = 'employee_program'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employeeID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'), nullable=False)
    programID = db.Column(db.Integer, db.ForeignKey('program.programID'), nullable=False)

class EmployeeArea(db.Model):
    __tablename__ = 'employee_area'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employeeID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'), nullable=False)
    areaID = db.Column(db.Integer, db.ForeignKey('area.areaID'), nullable=False)

class EmployeeFolder(db.Model):
    __tablename__ = 'employee_folder'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employeeID = db.Column('employeeid', db.String(10), db.ForeignKey('employee.employeeID', ondelete='CASCADE'), nullable=False)
    folderPath = db.Column('folderPath', db.String(500), nullable=False)

class AreaReference(db.Model):
    _tablename_ = 'area_reference'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    areaName = db.Column(db.String(120), nullable=False) 
    areaNum = db.Column(db.String(25), nullable=False)

    # Relationships to junction tables
    # employee_programs = db.relationship("EmployeeProgram", backref="employeeID")
    # employee_areas = db.relationship("EmployeeArea", backref="employeeID")
    # employee_folders = db.relationship("EmployeeFolder", backref="employeeID")

# class AccreditationCycle(db.Model):
#     __tablename__ = 'accreditationCycle'

#     cycleID = db.Column(db.Integer, primary_key=True, nullable=False)
#     programID = db.Column(db.Integer, db.ForeignKey('program.programID'), nullable=False)
#     templateID = db.Column(db.Integer, db.ForeignKey('template.templateID'), nullable=False)
#     cycleName = db.Column(db.String(255), nullable=False)
#     startDate = db.Column(db.Date, nullable=False)
#     endDate = db.Column(db.Date, nullable=False)
#     status = db.Column(db.String(50), nullable=False)  # e.g., 'active', 'archived'                  
    
class Template(db.Model):
    __tablename__ = 'template'

    templateID = db.Column(db.Integer, primary_key=True, nullable=False, autoincrement=True)
    templateName = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)    
    createdBy = db.Column(db.String(10), db.ForeignKey('employee.employeeID'), nullable=False)
    createdAt = db.Column(db.DateTime, default=datetime.utcnow)
    isApplied = db.Column(db.Boolean, default=False)
    archived = db.Column(db.Boolean, default=False)
    isApplied = db.Column(db.Boolean, default=False)
    archived = db.Column(db.Boolean, default=False)
    
    programs = db.relationship("Program", back_populates="template", lazy=True)
    employee = db.relationship("Employee", backref="templates")    
    areas = db.relationship("AreaBlueprint", backref="template", cascade="all, delete-orphan")

class AreaBlueprint(db.Model):
    __tablename__ = "areaBlueprint"
    areaBlueprintID = db.Column(db.Integer, primary_key=True)
    areaName = db.Column(db.String(255), nullable=False)
    areaNum = db.Column(db.String(10))
    templateID = db.Column(db.Integer, db.ForeignKey("template.templateID"))


    subareas = db.relationship("SubareaBlueprint", backref="area", cascade="all, delete-orphan")

class SubareaBlueprint(db.Model):
    __tablename__ = "subareaBlueprint"
    subareaBlueprintID = db.Column(db.Integer, primary_key=True)
    subareaName = db.Column(db.String(255), nullable=False)
    areaBlueprintID = db.Column(db.Integer, db.ForeignKey("areaBlueprint.areaBlueprintID"))
    criteria = db.relationship("CriteriaBlueprint", backref="subarea", cascade="all, delete-orphan")
    
    

class CriteriaBlueprint(db.Model):
    __tablename__ = "criteriaBlueprint"
    criteriaBlueprintID = db.Column(db.Integer, primary_key=True)
    criteriaContent = db.Column(db.Text, nullable=False)
    criteriaType = db.Column(db.String(50))
    subareaBlueprintID = db.Column(db.Integer, db.ForeignKey("subareaBlueprint.subareaBlueprintID"))


class AppliedTemplate(db.Model):
    __tablename__ = "appliedTemplate"

    appliedTemplateID = db.Column(db.Integer, primary_key=True)
    programID = db.Column(db.Integer, db.ForeignKey("program.programID"))
    templateID = db.Column(db.Integer, db.ForeignKey("template.templateID"))
    templateName = db.Column(db.String(100))
    description = db.Column(db.Text)
    appliedAt = db.Column(db.DateTime, default=datetime.utcnow)
    appliedBy = db.Column(db.Integer, db.ForeignKey("employee.employeeID"))

    areas = db.relationship("Area", back_populates="appliedTemplate", cascade="all, delete-orphan")


class Area(db.Model):
    __tablename__ = 'area'

    areaID = db.Column(db.Integer, primary_key=True, nullable=False)
    templateID = db.Column(db.Integer, db.ForeignKey('template.templateID'), nullable=True)
    areaBlueprintID = db.Column(db.Integer, db.ForeignKey("areaBlueprint.areaBlueprintID"))
    areaBlueprintID = db.Column(db.Integer, db.ForeignKey("areaBlueprint.areaBlueprintID"))
    appliedTemplateID = db.Column(db.Integer, db.ForeignKey("appliedTemplate.appliedTemplateID", ondelete="CASCADE"), nullable=False)
    instID = db.Column(db.Integer, db.ForeignKey('institute.instID'), nullable=True)
    programID = db.Column(db.Integer, db.ForeignKey('program.programID'), nullable=False)
    areaName = db.Column(db.String(100))
    areaNum = db.Column(db.String(10))
    progress = db.Column(db.Integer)
    subareaID = db.Column(db.Integer)
    rating = db.Column(db.Float)
    archived = db.Column(db.Boolean, default=False)


    appliedTemplate = db.relationship("AppliedTemplate", back_populates="areas")
    program = db.relationship("Program", back_populates="areas")
    subareas = db.relationship("Subarea", back_populates="area", cascade="all, delete-orphan")
    institute = db.relationship("Institute", back_populates="areas")    
    institute = db.relationship("Institute", back_populates="areas")    
    

class Program(db.Model):
    __tablename__ = 'program'

    programID = db.Column(db.Integer, primary_key=True, nullable=False)
    instID = db.Column(db.Integer, db.ForeignKey('institute.instID'), nullable=True)
    templateID = db.Column(db.Integer, db.ForeignKey('template.templateID'), nullable=True)
    templateID = db.Column(db.Integer, db.ForeignKey('template.templateID'), nullable=True)
    employeeID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'))
    programCode = db.Column(db.String(20))
    programName = db.Column(db.String(100))
    programColor = db.Column(db.String(30))

    dean = db.relationship("Employee", foreign_keys=[employeeID], backref="programs")
    institute = db.relationship("Institute", back_populates="programs")
    areas = db.relationship("Area", back_populates="program", cascade="all, delete-orphan")
    template = db.relationship("Template", back_populates="programs")
    template = db.relationship("Template", back_populates="programs")
    


class Subarea(db.Model):
    __tablename__ = 'subarea'

    subareaID = db.Column(db.Integer, primary_key=True, nullable=False)
    areaID = db.Column(db.Integer, db.ForeignKey('area.areaID'), nullable=False)
    subareaBlueprintID = db.Column(db.Integer, db.ForeignKey("subareaBlueprint.subareaBlueprintID"))
    subareaBlueprintID = db.Column(db.Integer, db.ForeignKey("subareaBlueprint.subareaBlueprintID"))
    subareaName = db.Column(db.String(100))
    criteriaID = db.Column(db.Integer)
    rating = db.Column(db.Float)
    archived = db.Column(db.Boolean, default=False)

    area = db.relationship("Area", back_populates="subareas")

    criteria = db.relationship("Criteria", back_populates="subarea", cascade="all, delete-orphan")  
    criteria = db.relationship("Criteria", back_populates="subarea", cascade="all, delete-orphan")  

class Criteria(db.Model):
    __tablename__ = 'criteria'

    criteriaID = db.Column(db.Integer, primary_key=True, nullable=False, autoincrement=True)
    subareaID = db.Column(db.Integer, db.ForeignKey('subarea.subareaID'), nullable=False)
    criteriaBlueprintID = db.Column(db.Integer, db.ForeignKey("criteriaBlueprint.criteriaBlueprintID"))
    criteriaBlueprintID = db.Column(db.Integer, db.ForeignKey("criteriaBlueprint.criteriaBlueprintID"))
    criteriaContent = db.Column(db.Text)
    criteriaType = db.Column(db.String(50))
    rating = db.Column(db.Float)
    isDone = db.Column(db.Boolean, default=False)
    docID = db.Column(db.Integer, db.ForeignKey('document.docID'), nullable=False)
    archived = db.Column(db.Boolean, default=False)

    subarea = db.relationship("Subarea", back_populates="criteria")    
    document = db.relationship("Document", back_populates="criteria")
    
    # Relationship to deadlines
    deadlines = db.relationship('Deadline', secondary='deadline_criteria', back_populates='criteria')

class Document(db.Model):
    __tablename__ = 'document'

    docID = db.Column(db.Integer, primary_key=True, nullable=False)
    employeeID = db.Column(db.String(10), nullable=False)
    docName = db.Column(db.String(150), nullable=False)
    docType = db.Column(db.String(50), nullable=False)    
    docPath = db.Column(db.Text)
    isApproved = db.Column(db.Boolean)
    approvedBy = db.Column(db.String(10), db.ForeignKey('employee.employeeID'))
    evaluate_at = db.Column(db.DateTime)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    content = db.Column(db.Text)
    search_vector = db.Column(TSVECTOR)
    tags = db.Column(ARRAY(db.String))
    embedding = db.Column(Vector(384)) 
    predicted_rating = db.Column(db.Float)
    predicted_probability = db.Column(db.Float)
    similar_docs = db.Column(db.JSON)

    criteria = db.relationship("Criteria", back_populates="document")

class Institute(db.Model):
    __tablename__ = 'institute'

    instID = db.Column(db.Integer, primary_key=True, nullable=False)
    employeeID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'))
    instCode = db.Column(db.String(50), nullable=False)
    instName = db.Column(db.String(100), nullable=False)
    instPic = db.Column(db.Text)

    dean = db.relationship("Employee", backref="institutes", foreign_keys=[employeeID])
    programs = db.relationship("Program", back_populates="institute", cascade="all, delete-orphan")
    areas = db.relationship("Area", back_populates="institute")    

class Deadline(db.Model):
    __tablename__ = 'deadline'

    deadlineID = db.Column(db.Integer, primary_key=True, nullable=False)    
    criteriaID = db.Column(db.Integer, db.ForeignKey('criteria.criteriaID'), nullable=True)
    programID = db.Column(db.Integer, nullable=False)
    areaID = db.Column(db.Integer, nullable=False)
    content = db.Column(db.Text, nullable=False)
    due_date = db.Column(db.Date, nullable=False)       

    # Relationship to criteria via junction table
    criteria = db.relationship('Criteria', secondary='deadline_criteria', back_populates='deadlines')


class DeadlineCriteria(db.Model):
    __tablename__ = 'deadline_criteria'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    deadlineID = db.Column(db.Integer, db.ForeignKey('deadline.deadlineID', ondelete="CASCADE"))
    criteriaID = db.Column(db.Integer, db.ForeignKey('criteria.criteriaID', ondelete="CASCADE"))

    criteria = db.relationship("Criteria", backref="deadline_criteria")

class AuditLog(db.Model):
    __tablename__ = 'audit_log'

    logID = db.Column(db.Integer, primary_key=True, nullable=False)
    employeeID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'), nullable=False)
    action = db.Column(db.String(255))
    createdAt = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
class Announcement(db.Model):
    __tablename__ = 'announcement'

    announceID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    employeeID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'), nullable=False)
    announceTitle = db.Column(db.String(255))
    announceText = db.Column(db.Text)
    duration = db.Column(db.Date)

# Messaging System Models
class Conversation(db.Model):
    __tablename__ = 'conversation'
    
    conversationID = db.Column(db.Integer, primary_key=True, nullable=False)
    conversationName = db.Column(db.String(100))  # For group chats
    conversationType = db.Column(db.String(20), nullable=False)  # 'direct' or 'group'
    createdBy = db.Column(db.String(50), db.ForeignKey('employee.employeeID'), nullable=False)
    createdAt = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    isActive = db.Column(db.Boolean, default=True)
    
    # Relationships
    creator = db.relationship("Employee", backref="created_conversations")
    messages = db.relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    participants = db.relationship("ConversationParticipant", back_populates="conversation", cascade="all, delete-orphan")

class ConversationParticipant(db.Model):
    __tablename__ = 'conversation_participant'
    
    participantID = db.Column(db.Integer, primary_key=True, nullable=False)
    conversationID = db.Column(db.Integer, db.ForeignKey('conversation.conversationID'), nullable=False)
    employeeID = db.Column(db.String(50), db.ForeignKey('employee.employeeID'), nullable=False)
    joinedAt = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    lastReadAt = db.Column(db.DateTime)
    isActive = db.Column(db.Boolean, default=True)
    
    # Relationships
    conversation = db.relationship("Conversation", back_populates="participants")
    employee = db.relationship("Employee", backref="conversation_participations")

class Message(db.Model):
    __tablename__ = 'message'
    
    messageID = db.Column(db.Integer, primary_key=True, nullable=False)
    conversationID = db.Column(db.Integer, db.ForeignKey('conversation.conversationID'), nullable=False)
    senderID = db.Column(db.String(50), db.ForeignKey('employee.employeeID'), nullable=False)
    messageContent = db.Column(db.Text, nullable=False)
    messageType = db.Column(db.String(20), default='text')  # 'text', 'file', 'image'
    sentAt = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    editedAt = db.Column(db.DateTime)
    isDeleted = db.Column(db.Boolean, default=False)
    
    # Relationships
    conversation = db.relationship("Conversation", back_populates="messages")
    sender = db.relationship("Employee", backref="sent_messages")


class MessageDeletion(db.Model):
    __tablename__ = 'message_deletion'

    id = db.Column(db.Integer, primary_key=True, nullable=False)
    messageID = db.Column(db.Integer, db.ForeignKey('message.messageID'), nullable=False)
    employeeID = db.Column(db.String(50), db.ForeignKey('employee.employeeID'), nullable=False)
    deletedAt = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Notification(db.Model):
    __tablename__ = 'notification'
    
    notificationID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    recipientID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'), nullable=False)
    senderID = db.Column(db.String(10), db.ForeignKey('employee.employeeID'), nullable=True)  # Null for system notifications
    type = db.Column(db.String(50), nullable=False)  # 'message', 'announcement', 'system'
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    isRead = db.Column(db.Boolean, default=False)
    createdAt = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    link = db.Column(db.String(255))  # Optional link to related page
    
    # Relationships
    recipient = db.relationship("Employee", foreign_keys=[recipientID], backref="received_notifications")
    sender = db.relationship("Employee", foreign_keys=[senderID], backref="sent_notifications")

