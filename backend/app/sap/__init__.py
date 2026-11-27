"""Connections to SAP systems.

Every connector here is real code that switches on when its SAP service is
bound (on SAP BTP Cloud Foundry, through VCAP_SERVICES) or configured through
environment variables. Without a connection the app keeps working: messages
for SAP systems are prepared and held in the outbox, and the status page says
plainly that nothing was sent.
"""
