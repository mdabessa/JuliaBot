from random import randint
import discord
import modules.database as db
import modules.entity as entity


category = 'Economia'
entity.Command.newcategory(category, ':coin:Economia.')


async def coins(message, commandpar, connection, bot):
    if len(message.mentions) >= 1 and len(message.mentions) <=3:
        for mentioned in message.mentions:
            points = db.getpoints(mentioned.id, message.guild.id, connection)
            await message.channel.send(f'{mentioned.name} possui `{points}` coins.')

    else:
        points = db.getpoints(message.author.id, message.guild.id, connection)
        await message.channel.send(f'{message.author.mention}, você possui `{points}` coins.')
entity.Command(name='coins', func=coins, category=category, desc='Verificar os pontos.', args=[['pessoa', 'º']])


async def coinsrank(message, commandpar, connection, bot):
    rank = db.rankpoints(message.guild.id, connection)
    if rank == None:   
        raise entity.CommandError('Não foi possivel execultar esta ação!')

    emb = discord.Embed(title='Rank', color=0xe6dc56)
    for num, i in enumerate(rank):
        user = bot.get_user(int(i[1]))
        points = i[2]

        if num == 0:
            medal = ':first_place:'
        if num == 1:
            medal = ':second_place:'
        if num == 2:
            medal = ':third_place:'
        if num == 3:
            medal = ':four:'
        if num == 4:
            medal = ':five:'
        

        emb.add_field(name=f'{medal}{user.name}', value=f':coin:{points}c', inline=False)
    
    await message.channel.send(embed=emb)
entity.Command(name='rank', func=coinsrank, category=category, desc='Top coins do servidor.')


async def roulette(message, commandpar, connection, bot):
    if commandpar != None:
        roulettechance = 33 #x/100
        p = db.getpoints(message.author.id, message.guild.id, connection)

        if commandpar == 'all':
            points = p
        else:
            try:
                points = int(commandpar)
            except:
                raise entity.CommandError('Não posso roletar nada que não seja um `numero inteiro` :pensive:')

        if points < p:
            if randint(0,100) < roulettechance:
                db.addpoints(message.author.id,message.guild.id, points, connection)
                await message.channel.send(f'{message.author.mention} Ganhou `{points}` coins! :money_mouth:')
            else:
                db.subpoints(message.author.id, message.guild.id, points, connection)
                await message.channel.send(f'{message.author.mention} Perdeu `{points}` coins! :sob:')

        if points == p:
            if randint(0,100) < roulettechance:
                db.addpoints(message.author.id,message.guild.id, points, connection)
                await message.channel.send(f'{message.author.mention} roletou tudo e ganhou `{points}` coins, dobrando sua fortuna! :sunglasses:')
            else:
                db.subpoints(message.author.id, message.guild.id, points, connection)
                await message.channel.send(f'{message.author.mention} roletou tudo e perdeu `{points}` coins, zerando seus pontos! :rofl: :rofl: :rofl:')
        if points > p:
            raise entity.CommandError('Voce não possui pontos suficiente!')
    else:
        raise entity.CommandError('Quantos coins você quer roletar? :thinking:')
entity.Command(name='roulette', func=roulette, category=category, desc=f'Roletar pontos.', args=[['coins', '*']])


async def setcoins(message, commandpar, connection, bot):
    if commandpar != None:
        try:
            pointspar = int(commandpar.split()[0])
        except:
            raise entity.CommandError('Só `numeros inteiros` podem ser definidos como coins')

        try:
            if len(message.mentions) > 0:
                names = []
                for user in message.mentions:
                    names.append(user.name)
                    db.setpoints(user.id,message.guild.id,int(pointspar),connection)
                
                await message.channel.send(f'Coins definido como `{pointspar}` para : {", ".join(names)}')
            else:
                db.setpoints(message.author.id,message.guild.id,int(pointspar),connection)
                await message.channel.send(f'{message.author.mention} Seus Coins foram definido para `{pointspar}`')
        except:
            raise entity.CommandError('Não foi possivel realizar esta ação :worried:')

    else:
        raise entity.CommandError('Quantos coins ?')
entity.Command(name='setcoins', func=setcoins , category=category, desc=f'Definir os seus pontos, ou os dos usuarios marcados.', args=[['coins', '*'], ['pessoa', 'º']], perm=1)


async def addcoins(message, commandpar, connection, bot):
    if commandpar != None:
        try:
            pointspar = int(commandpar.split()[0])
        except:
            raise entity.CommandError('Pontos tem que ser um `numero inteiro`!')

        try:
            if len(message.mentions) > 0:
                names = []
                for user in message.mentions:
                    names.append(user.name)
                    db.addpoints(user.id,message.guild.id,int(pointspar), connection)
                
                await message.channel.send(f'`{pointspar}` Coins adicionados para : {", ".join(names)}')
            else:
                db.addpoints(message.author.id,message.guild.id,int(pointspar),connection)
                await message.channel.send(f'{message.author.mention} Foram adicionados `{pointspar}` coins.')
        except:
            raise entity.CommandError('Não foi possivel realizar esta ação :worried:')
    else:
        raise entity.CommandError('Quantos pontos?')
entity.Command(name='addcoins', func=addcoins , category=category, desc=f'Adicionar pontos.', args=[['coins', '*'], ['pessoa', 'º']], perm=1)


async def subcoins(message, commandpar, connection, bot):
    if commandpar != None:
        try:
            pointspar = int(commandpar.split()[0])
        except:
            raise entity.CommandError('Pontos tem que ser um `numero inteiro`!')

        try:
            if len(message.mentions) > 0:
                names = []
                for user in message.mentions:
                    names.append(user.name)
                    db.subpoints(user.id,message.guild.id,int(pointspar), connection)
                
                await message.channel.send(f'`{pointspar}` Coins foram removidos de : {", ".join(names)}')
            else:
                db.subpoints(message.author.id,message.guild.id,int(pointspar), connection)
                await message.channel.send(f'{message.author.mention} Foram removidos `{pointspar}` coins.')
        except:
            raise entity.CommandError('Não foi possivel realizar esta ação! :worried:')
    else:
        raise entity.CommandError('Quantos pontos?')
entity.Command(name='subcoins', func=subcoins , category=category, desc=f'Remover pontos.', args=[['coins', '*'], ['pessoa', 'º']], perm=1)


async def shop(message, commandpar, connection, bot):
    items = db.getshop(message.guild.id, connection)

    if len(items) == 0:
        await message.channel.send('Esse servidor não possui itens a venda!')

    else:
        emb = discord.Embed(title='Loja', color=0xe6dc56)

        for i in items:
            emb.add_field(name=f'{i[1]} - {i[2]}', value=f':coin:{i[3]}c', inline=True)
        
        emb.set_footer(text=f'{db.getserver(message.guild.id, connection)["prefix"]}buy [id]')
        await message.channel.send(embed=emb)
entity.Command(name='shop', func=shop, category=category, desc=f'Loja de itens')


async def shopadditem(message, commandpar, connection, bot):
    if commandpar == None:
        raise entity.CommandError('Falta parametros!')

    cmdpar = commandpar.split()
    if len(cmdpar) < 2:
        raise entity.CommandError('Falta parametros!')

    try:
        price = int(cmdpar[0])
    except:
        raise entity.CommandError('Qual é o preco do item?')
    
    item_name = ' '.join(cmdpar[1:])

    db.additem(message.guild.id, item_name, price, connection)
    await message.channel.send(f'Item: `{item_name}` foi adicionado a loja por `{price}` coins!')
entity.Command(name='additem', func=shopadditem, category=category, desc=f'Adicionar um item a loja!',args=[['preço', '*'], ['item', '*']], perm=1)


async def buyitem(message, commandpar, connection, bot):
    if commandpar == None:
        raise entity.CommandError('Qual item ira comprar ?')
    
    try:
        item = int(commandpar)
    except:
        raise entity.CommandError('O item tem que ser referenciado com o um `ID`.')

    items = db.getshop(message.guild.id, connection)
    
    marc = 0
    for i in items:
        if i[1] == item:
            marc = 1
            points = db.getpoints(message.author.id, message.guild.id, connection)

            if i[3] > points:
                raise entity.CommandError('Coins insuficientes!')

            db.subpoints(message.author.id, message.guild.id, i[3], connection)
            await message.channel.send(f'{message.author.mention} comprou `{i[1]} - {i[2]}` por `{i[3]}c`.')

    if marc == 0:
        raise entity.CommandError(f'{message.author.mention} o item `{commandpar}` não existe.')
entity.Command(name='buy', func=buyitem, category=category, desc=f'Comprar um item.', args=[['id do item', '*']])


async def shopdelitem(message, commandpar, connection, bot):
    if commandpar == None:
        raise entity.CommandError('Qual item irá deletar?')

    try:
        item = int(commandpar)
    except:
        raise entity.CommandError('O item tem que ser referenciado com o um `ID`.')

    items = db.getshop(message.guild.id, connection)

    marc = 0
    for i in items:
        if i[1] == item:
            marc = 1
            db.delitem(message.guild.id, item, connection)
            await message.channel.send(f'{message.author.mention} removeu o item `{i[1]} - {i[2]}` da loja!')

    if marc == 0:
        raise entity.CommandError(f'{message.author.mention} o item `{commandpar}` não existe.')
entity.Command(name='delitem', func=shopdelitem, category=category, desc=f'Deletar itens da loja.', args=[['id do item', '*']], perm=1)
