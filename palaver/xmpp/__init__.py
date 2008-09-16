

def jid_escape(nodeId):
    """
    Unescaped Character 	Encoded Character
    <space>             	\20
    "                   	\22
    \                   	\5c
    & 	                        \26
    ' 	                        \27
    / 	                        \2f
    : 	                        \3a
    < 	                        \3c
    > 	                        \3e
    @ 	                        \40
    """
    if nodeId is None:
        return

    newNode = nodeId

    newNode = newNode.replace("\\", '\\5c')
    newNode = newNode.replace(' ', "\\20")
    newNode = newNode.replace('"', '\\22')
    
    newNode = newNode.replace("&", '\\26')
    newNode = newNode.replace("'", '\\27')
    newNode = newNode.replace("/", '\\2f')
    newNode = newNode.replace(":", '\\3a')
    newNode = newNode.replace("<", '\\3c')
    newNode = newNode.replace(">", '\\3e')
    newNode = newNode.replace("@", '\\40')
    return newNode


def jid_unescape(nodeId):
    if nodeId is None:
        return
    newNode = nodeId

    newNode = newNode.replace("\\5c", '\\')
    newNode = newNode.replace("\\20", ' ')
    newNode = newNode.replace('\\22', '"')
    
    newNode = newNode.replace('\\26', "&")
    newNode = newNode.replace('\\27',"'")
    newNode = newNode.replace('\\2f', "/")
    newNode = newNode.replace('\\3a', ":")
    newNode = newNode.replace('\\3c', "<")
    newNode = newNode.replace('\\3e', ">")
    newNode = newNode.replace('\\40', "@")
    return newNode
