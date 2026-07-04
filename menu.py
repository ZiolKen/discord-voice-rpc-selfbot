import os, time, sys
from version import version
from color import color
class UI:

	@classmethod
	def slowPrinting(cls, text):
		for letter in text:
			time.sleep(.002)
			print(letter, end="", flush=True)
		print("")
	@classmethod
	def logo(cls):
		cls.slowPrinting("DISCORD VOICE & CUSTOM RPC SELFBOT")
		cls.slowPrinting(f"              {color.purple}Version: {version}{color.reset}")
		time.sleep(0.5)
		print()
